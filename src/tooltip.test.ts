/**
 * Tooltips: focus, hover, reduced motion, and a control with no sentence.
 *
 * The page markup is the real index.html. Fetch is stubbed only for the
 * detail pane. No shortcut is added.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import { mountPlayer } from "./player";
import { chordLabel, SHORTCUTS, type ShortcutId } from "./shortcuts";
import { state } from "./state";
import { installPage } from "./test-page";
import en from "../locales/en.json";
import es from "../locales/es.json";
import { PSEUDO, setLocale, t } from "./i18n";
import {
  applyStaticTooltips,
  installTooltips,
  missingTooltipLabels,
  refreshTooltips,
  resetTooltipState,
  setTooltip,
  TOOLTIP_HOVER_MS,
  TOOLTIP_ID,
} from "./tooltip";
import { playTip, tipText, tips, wizardPrimaryTip, type TipSpec } from "./tooltip-strings";
import { mountTrackList, paintRows } from "./virtual-scroll";
import { renderCrates, renderFiles, renderSessions, selectEntry, selectTrack } from "./views";

declare global {
  interface ImportMeta {
    glob(pattern: string, options: { query: "?raw"; import: "default"; eager: true }): Record<string, string>;
  }
}

function tip(): HTMLElement {
  const node = document.getElementById(TOOLTIP_ID);
  if (!(node instanceof HTMLElement)) throw new Error("missing tooltip");
  return node;
}

function pointer(type: "pointerover" | "pointerout", target: Element): void {
  target.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerType: "mouse" }));
}

function stubMotion(reduce: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

function expectCovered(): void {
  expect(missingTooltipLabels()).toEqual([]);
}

describe("tooltip behavior", () => {
  beforeEach(() => {
    resetTooltipState();
    installPage();
    applyStaticTooltips();
    installTooltips();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows on focus, describes the control, and restores the previous description", () => {
    const loops = document.getElementById("rekordbox-hot-loops");
    if (!(loops instanceof HTMLElement)) throw new Error("missing hot loops");
    expect(loops.getAttribute("aria-describedby")).toBe("rekordbox-hot-loops-help");
    loops.focus();
    expect(tip().hidden).toBe(false);
    expect(tip().textContent).toBe(tipText(tips.hotLoops));
    expect(loops.getAttribute("aria-describedby")).toBe(`rekordbox-hot-loops-help ${TOOLTIP_ID}`);
    expect(tip().getAttribute("role")).toBe("tooltip");

    const reload = document.getElementById("reload");
    if (!(reload instanceof HTMLElement)) throw new Error("missing reload");
    reload.focus();
    expect(loops.getAttribute("aria-describedby")).toBe("rekordbox-hot-loops-help");
    expect(reload.getAttribute("aria-describedby")).toBe(TOOLTIP_ID);
    expect(tip().textContent).toBe(tipText(tips.reload));
    reload.blur();
    expect(tip().hidden).toBe(true);
    expect(reload.hasAttribute("aria-describedby")).toBe(false);
  });

  it("waits on hover and shows immediately when reduced motion is requested", () => {
    stubMotion(false);
    vi.useFakeTimers();
    const reload = document.getElementById("reload");
    if (!(reload instanceof HTMLElement)) throw new Error("missing reload");
    pointer("pointerover", reload);
    expect(document.getElementById(TOOLTIP_ID)?.hidden ?? true).toBe(true);
    vi.advanceTimersByTime(TOOLTIP_HOVER_MS - 1);
    expect(document.getElementById(TOOLTIP_ID)?.hidden ?? true).toBe(true);
    vi.advanceTimersByTime(1);
    expect(tip().hidden).toBe(false);
    expect(tip().textContent).toBe(tipText(tips.reload));

    pointer("pointerout", reload);
    expect(tip().hidden).toBe(true);
    stubMotion(true);
    pointer("pointerover", reload);
    expect(tip().hidden).toBe(false);
  });

  it("hides on Escape without cancelling the key", () => {
    const reload = document.getElementById("reload");
    if (!(reload instanceof HTMLElement)) throw new Error("missing reload");
    reload.focus();
    expect(tip().hidden).toBe(false);
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(tip().hidden).toBe(true);
  });

  it("uses the field tooltip when the pointer is on its label", () => {
    stubMotion(true);
    const label = document.querySelector("label.rekordbox-option");
    if (!(label instanceof HTMLElement)) throw new Error("missing memory cues label");
    pointer("pointerover", label);
    expect(tip().textContent).toBe(tipText(tips.memoryCues));
  });

  it("rejects a tooltip key that is not in the catalog", () => {
    const button = document.createElement("button");
    expect(() => setTooltip(button, { key: "tooltip.missing" as TipSpec["key"] })).toThrow(/Unknown tooltip/);
  });

  it("covers every static control and reports one whose sentence was removed", () => {
    expectCovered();
    const reload = document.getElementById("reload");
    reload?.removeAttribute("data-tooltip");
    expect(missingTooltipLabels().some((line) => line.includes("#reload"))).toBe(true);
  });
});

describe("rendered controls", () => {
  beforeEach(() => {
    resetTooltipState();
    installPage();
    applyStaticTooltips();
    installTooltips();
    state.tracks = [];
    state.byId = new Map();
    state.crates = [];
    state.crateTracks = new Map();
    state.rootId = null;
    state.activeCrate = "all";
    state.query = "";
    state.crateQuery = "";
    state.expanded = new Set();
    state.space = "Serato Library";
    state.mode = "crates";
    state.writable = true;
    state.serato = { writable: true, file_manager: "Finder", message: "Serato is quit." };
    state.historySessions = [];
    state.historyId = null;
    state.entries = [];
    state.duplicateGroups = [];
    state.selectedId = null;
    state.view = [];
    state.filesPath = "";
    state.filesParent = null;
    state.filesEntries = [];
    state.filesSelected = new Set();
    state.filesPick = null;
    state.filesLoading = false;
    state.filesError = "";
    state.filesMessage = "";
    state.filesTruncated = false;
    state.filesAtRoots = false;
    state.filesRoots = [];
    state.filesBreadcrumb = [];
    state.filesElsewhere = false;
    state.filesSearching = false;
    state.filesActive = 0;
    state.request = 0;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("covers crates, files, sessions, rows, and an empty music-folder list", () => {
    state.rootId = 1;
    state.crates = [
      { id: 2, name: "House", parent: 1, order: 0 },
      {
        id: 3,
        name: "Deep",
        parent: 2,
        order: 0,
        smart: true,
        rules: { rules: [{ attribute: "bpm", operation: "greater", value: "120" }], conjunction: "AND" },
      },
    ];
    state.crateTracks = new Map([[2, new Set([1])], [3, new Set([1])]]);
    state.expanded = new Set([2]);
    state.activeCrate = 3;
    state.historySessions = [{ id: 4, name: "Friday", played: 1 }];
    state.filesPath = "/music/House";
    state.filesParent = "/music";
    state.filesBreadcrumb = [
      { name: "Music", path: "/music" },
      { name: "House", path: "/music/House" },
    ];
    state.filesEntries = [
      { name: "Sets", path: "/music/House/Sets", kind: "dir" },
      { name: "Away", path: "/mnt/usb/Away", kind: "dir", missing: true },
      { name: "night.mp3", path: "/music/House/night.mp3", kind: "file" },
      { name: "alias", path: "/music/House/alias", kind: "link" },
    ];
    state.view = [
      { id: 1, name: "Night", artist: "Ada" },
      { id: 9, name: "Friday", entry: true },
    ];
    state.mode = "files";
    renderFiles();
    state.mode = "crates";
    renderCrates();
    renderSessions();
    mountTrackList();
    paintRows();
    expectCovered();
    expect(document.querySelector("#crate-list [data-id='all']")?.getAttribute("data-tooltip")).toContain("Ctrl/Cmd+1");
    const fileTips = [...document.querySelectorAll(".files-open")].map((node) => node.getAttribute("data-tooltip") ?? "");
    expect(fileTips.some((text) => text.includes("Sets"))).toBe(true);
    expect(fileTips.some((text) => text.includes("Connect the drive"))).toBe(true);
    expect(document.querySelector(".files-kind")?.getAttribute("data-tooltip")).toContain("shortcut");

    state.mode = "files";
    state.filesAtRoots = true;
    state.filesRoots = [];
    state.filesEntries = [];
    state.filesBreadcrumb = [];
    renderFiles();
    expectCovered();
    expect(document.getElementById("files-run-setup")?.getAttribute("data-tooltip")).toBe(tipText(tips.runSetup));
  });

  it("covers the player, the detail pane, related tracks, and a history row", async () => {
    mountPlayer();
    expectCovered();
    expect(document.querySelector("[aria-label='Zoom in']")?.getAttribute("data-tooltip")).toBe(tipText(tips.zoomIn));
    expect(document.querySelector("[aria-label='Zoom in']")?.getAttribute("data-tooltip")).not.toBe("Zoom in");
    expect(document.querySelector(".waveform-overview")?.getAttribute("data-tooltip")).toContain("Left arrow");

    state.mode = "duplicates";
    state.writable = true;
    state.selectedId = 1;
    state.duplicateGroups = [{ ids: [1, 2] }];
    state.crates = [{ id: 2, name: "House", parent: 1, order: 0 }];
    state.tracks = [
      { id: 1, name: "Night", artist: "Ada" },
      { id: 2, name: "Alpha", artist: "Bea" },
    ];
    const payload: Track = {
      id: 1,
      name: "Night",
      title: "Night",
      artist: "Ada",
      file_on_disk: true,
      resolved_path: "/music/night.mp3",
      in_prepare: false,
      crate_ids: [2],
      serato: { writable: true, file_manager: "Finder", message: "Serato is quit." },
      edit: { name: "Night", artist: "Ada", comments: "", color: 0xffffff, is_beatgrid_locked: false },
      copies: [{ id: 2, file: "night-2.mp3" }],
      groups: [{ name: "Search copies", fields: [{ label: "Title", column: "name", display: "Night" }] }],
    };
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/related")) {
        return Promise.resolve(new Response(JSON.stringify({
          saved: [{ mutual: true, track: { title: "Alpha", artist: "Bea", asset_id: 2, in_library: true } }],
          suggested: [{ title: "Beta", artist: "Cy", asset_id: 3, reasons: ["same key"] }],
          crate_name: "Related - Night",
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.includes("/api/track")) {
        return Promise.resolve(new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    await selectTrack(1);
    await vi.waitUntil(() => document.querySelector("[data-related-crate]") !== null);
    const search = document.querySelector<HTMLInputElement>(".related-search input");
    if (!search) throw new Error("missing related search");
    search.value = "Alpha";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector<HTMLButtonElement>(".related-results button")?.click();
    expectCovered();
    expect(document.querySelector(".detail-play")?.getAttribute("data-tooltip")).toContain("Space");
    expect(document.querySelector(".player-play")?.getAttribute("data-tooltip")).toContain("Space");

    state.entries = [{ id: 9, name: "Friday", artist: "Ada", file: "a.mp3", asset_id: 1 }];
    selectEntry(9);
    expectCovered();
    expect(document.body.textContent).toContain("Open in library");
  });
});

describe("tooltip copy", () => {
  it("names every shortcut on the control that uses it", () => {
    const mentioned: Record<ShortcutId, string> = {
      "focus-search": tipText(tips.search),
      "quick-open": tipText(tips.quickOpen),
      dismiss: tipText(tips.search),
      "cheat-sheet": tipText(tips.shortcuts),
      "list-previous": tipText(tips.trackList),
      "list-next": tipText(tips.trackList),
      "list-open": tipText(tips.trackList),
      "play-pause": tipText(playTip("Play", "Night")),
      "seek-back": tipText(tips.seek),
      "seek-forward": tipText(tips.seek),
      "view-library": tipText(tips.allTracks),
      "view-crates": tipText(tips.viewCrates),
      "view-files": tipText(tips.viewFiles),
      "view-history": tipText(tips.viewHistory),
      "view-snapshots": tipText(tips.viewSnapshots),
    };
    for (const shortcut of SHORTCUTS) {
      const text = mentioned[shortcut.id as ShortcutId];
      for (const chord of shortcut.keys) {
        const label = chordLabel(chord);
        if (label === "/") expect(text, shortcut.id).toContain(" or /");
        else expect(text, shortcut.id).toContain(label);
      }
    }
    expect(tipText(tips.filesSearch)).toContain("Ctrl/Cmd+F");
    expect(tipText(tips.overview)).toContain("Left arrow");
    expect(tipText(tips.overview)).toContain("Right arrow");
    expect(tipText(wizardPrimaryTip("open-library", false))).toBe("Finish setup and open the library.");
    expect(tipText(wizardPrimaryTip("take-snapshot", true))).toBe("Saving a safety copy of the library.");
  });

  it("creates buttons and fields only through the tooltip helpers", () => {
    const pattern = /document\.createElement\(\s*["'](button|input|select|textarea)["']\s*\)/;
    const sources = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true });
    const offenders = Object.entries(sources)
      .filter(([path, text]) => !path.endsWith("tooltip.ts") && !path.endsWith(".test.ts") && pattern.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it("has every tooltip key in every locale", () => {
    const keys = Object.keys(en).filter((key) => key.startsWith("tooltip."));
    expect(keys.length).toBeGreaterThan(100);
    const catalogs = { en, es };
    for (const [code, catalog] of Object.entries(catalogs)) {
      for (const key of keys) {
        const message = catalog[key as keyof typeof catalog];
        expect(typeof message, `${code} ${key}`).toBe("string");
        expect(String(message).trim(), `${code} ${key}`).not.toBe("");
      }
      const extras = Object.keys(catalog).filter((key) => key.startsWith("tooltip.") && !keys.includes(key));
      expect(extras, code).toEqual([]);
    }
    const copied = keys.filter((key) => en[key as keyof typeof en] === es[key as keyof typeof es]);
    expect(copied).toEqual([]);
  });
});

describe("tooltip languages", () => {
  beforeEach(() => {
    resetTooltipState();
    installPage();
    document.documentElement.lang = "en";
    applyStaticTooltips();
    installTooltips();
  });

  afterEach(() => {
    document.documentElement.lang = "en";
  });

  it("renders Spanish and the pseudo-locale, and refreshes an open tooltip", () => {
    const search = document.getElementById("search");
    if (!(search instanceof HTMLElement)) throw new Error("missing search");
    expect(search.dataset.tooltip).toBe(t("tooltip.search"));
    search.focus();
    expect(tip().textContent).toBe(t("tooltip.search"));

    setLocale("es");
    refreshTooltips();
    expect(search.dataset.tooltip).toBe(t("tooltip.search"));
    expect(search.dataset.tooltip).toContain("Busca pistas");
    expect(tip().textContent).toBe(search.dataset.tooltip);
    expect(document.querySelector("[data-view='crates']")?.getAttribute("data-tooltip")).toContain("cajas");

    setLocale(PSEUDO);
    refreshTooltips();
    const pseudo = search.dataset.tooltip ?? "";
    expect(pseudo.startsWith("[")).toBe(true);
    expect(pseudo.endsWith("]")).toBe(true);
    expect(pseudo).toContain("~");
    expect(pseudo).not.toContain("Search tracks");
    expect(tip().textContent).toBe(pseudo);
  });
});
