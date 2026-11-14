/**
 * Tag spellings: groups, preview, apply, and title cleanup.
 *
 * GET /api/tag-clusters lists genre and artist groups. POST preview
 * lists the rows a chosen spelling would rewrite. POST apply writes
 * through safe_write and remembers the spelling. Genre and Artist also
 * POST refresh-preview; Apply saved mappings POSTs refresh-apply.
 * Titles uses POST clean-preview and clean-apply. Audio files are not
 * rewritten. A newer load ignores a late response. TagsPanel paints
 * from HealthContext.
 *
 * Page text is in the locale catalogs under tags.*.
 */

import { createElement } from "react";
import { failureOf, postJSON, readJSON } from "../api";
import type { TagClusterGroup, TagClusterPlan, TagClusters } from "../api-types";
import { mountIsland, type IslandRoot } from "../../app/mount";
import { TagsPanel } from "../../pages/TagsPanel";
import { bridge } from "../bridge";
import { el } from "../dom";
import { emitHealth } from "./health-events";
import { serverMessage, t } from "../i18n";
import { state } from "../state";
import { setNotice } from "../ui/notice-store";
import {
  mappingWrittenSummary,
  previewSummary,
  titlesPreviewSummary,
  titlesWrittenSummary,
  writtenSummary,
  type TagField,
} from "./tags-view";

const TITLE_KEY = "clean";
const MAPPING_KEY = "saved";

let latest: TagClusters | null = null;
let titlePlan: TagClusterPlan | null = null;
let mappingPlan: TagClusterPlan | null = null;
const plans = new Map<string, TagClusterPlan>();
const selectedByKey = new Map<string, string>();
const openKeys = new Set<string>();
let field: TagField = "genre";
let status = "";
let panelBusy = false;
let actionKey = "";
let panelRoot: IslandRoot | undefined;
let panelHost: HTMLElement | null = null;

/**
 * Snapshot HealthProvider reads for Tag spellings.
 *
 * @returns Field, groups, plans, and busy flags.
 */
export function getTagsSnapshot(): {
  tagsField: TagField;
  tagsClusters: TagClusters | null;
  titlePlan: TagClusterPlan | null;
  mappingPlan: TagClusterPlan | null;
  tagsPlans: ReadonlyMap<string, TagClusterPlan>;
  tagsSelected: ReadonlyMap<string, string>;
  tagsOpen: ReadonlySet<string>;
  tagsStatus: string;
  tagsBusy: boolean;
  tagsActionKey: string;
  tagsWritable: boolean;
} {
  return {
    tagsField: field,
    tagsClusters: latest,
    titlePlan,
    mappingPlan,
    tagsPlans: plans,
    tagsSelected: selectedByKey,
    tagsOpen: openKeys,
    tagsStatus: status,
    tagsBusy: panelBusy,
    tagsActionKey: actionKey,
    tagsWritable: state.writable,
  };
}

/**
 * Switch Genre, Artist, or Titles.
 *
 * Does not fetch. loadTags follows a field change from the panel.
 *
 * @param next Field to show.
 * @returns {void}
 */
export function setTagsField(next: TagField): void {
  field = next;
  emitHealth();
}

/**
 * Remember the radio for one cluster and drop its preview.
 *
 * @param key Cluster key.
 * @param value Stored spelling.
 * @returns {void}
 */
export function selectSpelling(key: string, value: string): void {
  selectedByKey.set(key, value);
  plans.delete(key);
  emitHealth();
}

/**
 * Mount Genre, Artist, Titles, Check again, and the report.
 *
 * Called once at startup. A later call remounts the same host.
 *
 * @returns {void}
 */
export function wireTags(): void {
  field = "genre";
  const panel = el("tags-panel");
  if (panelRoot && panelHost !== panel) {
    panelRoot.unmount();
    panelRoot = undefined;
  }
  panelHost = panel;
  panelRoot = mountIsland(panel, createElement(TagsPanel), panelRoot);
}

/**
 * Unmount the Tag spellings Data Grid island.
 *
 * Tests replace `document.body` between cases. Unmount first so the
 * Data Grid scheduler does not run after jsdom tears the window down.
 * A pending load is ignored so it does not look up a host that is gone.
 * Busy is cleared so the next mount is not stuck disabled.
 *
 * @returns {void}
 */
export function unmountTags(): void {
  state.tagsToken += 1;
  panelBusy = false;
  actionKey = "";
  if (!panelRoot) return;
  try {
    panelRoot.unmount();
  } catch {
    // installPage already dropped the host.
  }
  panelRoot = undefined;
  panelHost = null;
}

/**
 * Ask for spelling groups of the open space and field.
 *
 * The previous report stays on screen until this reply arrives. Genre,
 * Artist, Titles, and Check again are disabled while the request runs.
 *
 * @returns {Promise<void>}
 */
export async function loadTags(): Promise<void> {
  const token = ++state.tagsToken;
  plans.clear();
  selectedByKey.clear();
  openKeys.clear();
  beginBusy();
  let settle: "report" | "retry" | "none" = "none";
  try {
    if (field === "titles") {
      const payload = await postJSON<TagClusterPlan>("/api/tag-clusters", {
        action: "clean-preview",
        space: state.space,
      });
      if (token !== state.tagsToken) return;
      titlePlan = payload;
      latest = null;
      mappingPlan = null;
      status = titlesPreviewSummary(payload);
      settle = "report";
    } else {
      const response = await fetch(
        `/api/tag-clusters?space=${encodeURIComponent(state.space)}&field=${encodeURIComponent(field)}`,
      );
      if (token !== state.tagsToken) return;
      const payload = await readJSON<TagClusters>(response).catch((): null => null);
      if (token !== state.tagsToken) return;
      if (!response.ok || payload === null) {
        failStatus(serverMessage(payload, t("tags.unreadable")));
        settle = "retry";
        return;
      }
      latest = payload;
      titlePlan = null;
      mappingPlan = await readMappingPreview(token);
      if (token !== state.tagsToken) return;
      status = "";
      settle = "report";
    }
  } catch (error) {
    if (token !== state.tagsToken) return;
    if (error instanceof TypeError) failStatus(t("tags.unreachable"));
    else failStatus(failureOf(error).message);
    settle = "retry";
  } finally {
    if (token !== state.tagsToken) return;
    endBusy();
    emitHealth();
    if (settle === "retry") el("tags-refresh").focus();
    if (settle === "report") el("tags-report").focus();
  }
}

/**
 * Show a tags failure in the status line.
 *
 * The report already on screen stays. Focus moves to Check again.
 *
 * @param error Failure from loadTags.
 * @returns {void}
 */
export function showTagsFailure(error: unknown): void {
  const message = error instanceof Error && error.message
    ? error.message
    : t("tags.unreadable");
  failStatus(message);
  endBusy();
  el("tags-refresh").focus();
}

/**
 * Store groups and paint them.
 *
 * @param payload JSON from GET /api/tag-clusters.
 * @returns {void}
 */
export function renderTagsReport(payload: TagClusters): void {
  latest = payload;
  emitHealth();
}

/**
 * Paint the last report again in the active language.
 *
 * locale-wiring calls this on a language change. Nothing is fetched.
 *
 * @returns {void}
 */
export function repaintTags(): void {
  emitHealth();
}

/**
 * Preview the rows a chosen spelling would rewrite.
 *
 * @param key Cluster key.
 * @returns {Promise<void>}
 */
export async function previewGroup(key: string): Promise<void> {
  const group = groupByKey(key);
  const value = selectedValue(key);
  if (!group || !value) return;
  actionKey = key;
  emitHealth();
  try {
    const plan = await postJSON<TagClusterPlan>("/api/tag-clusters", {
      action: "preview",
      space: state.space,
      field: field === "titles" ? "genre" : field,
      value,
    });
    plans.set(key, plan);
    status = previewSummary(plan);
    emitHealth();
    applyButton(key)?.focus();
  } catch (error) {
    failStatus(failureOf(error).message);
  } finally {
    actionKey = "";
    emitHealth();
  }
}

/**
 * Write the previewed spelling through safe_write.
 *
 * @param key Cluster key.
 * @returns {Promise<void>}
 */
export async function applyGroup(key: string): Promise<void> {
  const plan = plans.get(key);
  const value = selectedValue(key);
  if (!plan || !value || plan.value !== value || !plan.changes.length || !state.writable) return;
  actionKey = key;
  panelBusy = true;
  beginBusy();
  emitHealth();
  try {
    const written = await postJSON<TagClusterPlan>("/api/tag-clusters", {
      action: "apply",
      space: state.space,
      field: field === "titles" ? "genre" : field,
      value,
    });
    await bridge.reloadLibrary();
    actionKey = "";
    panelBusy = false;
    endBusy();
    await loadTags();
    status = writtenSummary(written);
    emitHealth();
  } catch (error) {
    failApply(error);
  } finally {
    actionKey = "";
    panelBusy = false;
    endBusy();
    emitHealth();
  }
}

/**
 * Write saved spelling mappings through safe_write.
 *
 * @returns {Promise<void>}
 */
export async function applyMappings(): Promise<void> {
  const plan = mappingPlan;
  if (!plan || !plan.changes.length || !state.writable) return;
  actionKey = MAPPING_KEY;
  panelBusy = true;
  beginBusy();
  emitHealth();
  try {
    const written = await postJSON<TagClusterPlan>("/api/tag-clusters", {
      action: "refresh-apply",
      space: state.space,
    });
    await bridge.reloadLibrary();
    actionKey = "";
    panelBusy = false;
    endBusy();
    await loadTags();
    status = mappingWrittenSummary(written);
    emitHealth();
  } catch (error) {
    failApply(error);
  } finally {
    actionKey = "";
    panelBusy = false;
    endBusy();
    emitHealth();
  }
}

/**
 * Write cleaned titles through safe_write.
 *
 * @returns {Promise<void>}
 */
export async function applyTitles(): Promise<void> {
  const plan = titlePlan;
  if (!plan || !plan.changes.length || !state.writable) return;
  actionKey = TITLE_KEY;
  panelBusy = true;
  beginBusy();
  emitHealth();
  try {
    const written = await postJSON<TagClusterPlan>("/api/tag-clusters", {
      action: "clean-apply",
      space: state.space,
    });
    await bridge.reloadLibrary();
    actionKey = "";
    panelBusy = false;
    endBusy();
    await loadTags();
    status = titlesWrittenSummary(written);
    emitHealth();
  } catch (error) {
    failApply(error);
  } finally {
    actionKey = "";
    panelBusy = false;
    endBusy();
    emitHealth();
  }
}

function beginBusy(): void {
  panelBusy = true;
  el("tags-panel").setAttribute("aria-busy", "true");
  status = field === "titles" ? t("tags.checkingTitles") : t("tags.checking");
  emitHealth();
}

function endBusy(): void {
  panelBusy = false;
  el("tags-panel").setAttribute("aria-busy", "false");
  emitHealth();
}

function asMappingPlan(payload: unknown): TagClusterPlan | null {
  if (payload === null || typeof payload !== "object") return null;
  const plan = payload as TagClusterPlan;
  if (!Array.isArray(plan.changes)) return null;
  return plan;
}

async function readMappingPreview(token: number): Promise<TagClusterPlan | null> {
  try {
    const payload = await postJSON<TagClusterPlan>("/api/tag-clusters", {
      action: "refresh-preview",
      space: state.space,
    });
    if (token !== state.tagsToken) return null;
    return asMappingPlan(payload);
  } catch {
    if (token !== state.tagsToken) return null;
    return null;
  }
}

function failStatus(message: string): void {
  status = message;
  emitHealth();
}

function failApply(error: unknown): void {
  const failed = failureOf(error);
  failStatus(failed.message);
  setNotice(failed.message, "error");
  if (failed.status === 409) {
    bridge.lockDown(error);
  }
}

function groupByKey(key: string): TagClusterGroup | undefined {
  return latest?.groups?.find((group) => group.key === key);
}

function selectedValue(key: string): string {
  const group = groupByKey(key);
  return selectedByKey.get(key) ?? group?.suggested ?? "";
}

function applyButton(key: string): HTMLButtonElement | null {
  return el("tags-report").querySelector(`[data-tags-action="apply"][data-key="${cssEscape(key)}"]`);
}

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(value);
  return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}
