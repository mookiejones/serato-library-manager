/**
 * App version in the rail footer and in Settings.
 *
 * The text comes from GET /api/version. A failed request leaves the
 * footer empty and says Version unavailable in About. The page does
 * not show the server's error text.
 */

import { getVersion } from "./api";
import type { VersionPayload } from "./api-types";
import { el } from "./dom";
import { t } from "./i18n";

/** English text for the unavailable state. The page shows t("version.unavailable"). */
export const VERSION_UNAVAILABLE = "Version unavailable";

let copyText = "";
let painted: string | null | undefined;

/**
 * Turn the version object into the line the page shows.
 *
 * A release is the tag, such as v1.4.2. A numeric version without a
 * leading v, such as 0.0.0+dev, gains that v. A development build adds
 * the first seven characters of commit when that hex is not already in
 * the version text.
 *
 * @param info The GET /api/version object.
 * @returns The footer and About label.
 */
export function versionLabel(info: VersionPayload): string {
  const version = formatVersion(info.version);
  if (info.source === "release") return version;
  const commit = shortCommit(info.commit);
  if (!commit || version.toLowerCase().includes(commit)) return version;
  return `${version} · ${commit}`;
}

function formatVersion(version: string): string {
  const trimmed = version.trim();
  if (/^\d+\.\d+\.\d+/.test(trimmed)) return `v${trimmed}`;
  return trimmed;
}

function shortCommit(commit: string | null): string | null {
  if (commit === null) return null;
  const trimmed = commit.trim().toLowerCase();
  if (!/^[0-9a-f]{7,40}$/.test(trimmed)) return null;
  return trimmed.slice(0, 7);
}

function paint(label: string | null): void {
  painted = label;
  const footer = el("app-version");
  const about = el("about-version");
  el("version-copy-status").textContent = "";
  if (!label) {
    copyText = "";
    footer.hidden = true;
    footer.replaceChildren();
    about.textContent = t("version.unavailable");
    return;
  }
  copyText = label;
  footer.hidden = false;
  footer.replaceChildren();
  const name = document.createElement("span");
  name.className = "visually-hidden";
  name.textContent = `${t("version.app")} `;
  const value = document.createElement("span");
  value.textContent = label;
  footer.append(name, value);
  about.textContent = label;
}

/**
 * Paint the footer and About again in the active language.
 *
 * Uses the last version read. Before the first read it does nothing.
 *
 * @returns Nothing.
 */
export function repaintVersion(): void {
  if (painted === undefined) return;
  paint(painted);
}

/**
 * Read GET /api/version and paint the footer and About.
 *
 * A failure, including a body that is not the version object, paints
 * the unavailable state. This function does not reject.
 *
 * @returns Nothing.
 */
export async function loadVersion(): Promise<void> {
  try {
    paint(versionLabel(await getVersion()));
  } catch {
    paint(null);
  }
}

/**
 * Copy the version line and say Copied.
 *
 * When the version was not read, the live region says Version
 * unavailable and nothing is written to the clipboard. A clipboard
 * failure says Couldn't copy the version. The region does not show
 * the exception text.
 *
 * @returns Nothing.
 */
export async function copyVersion(): Promise<void> {
  const status = el("version-copy-status");
  if (!copyText) {
    status.textContent = t("version.unavailable");
    return;
  }
  const writeText = navigator.clipboard?.writeText;
  if (!writeText || !window.isSecureContext) {
    status.textContent = t("version.copyFailed");
    return;
  }
  try {
    await writeText.call(navigator.clipboard, copyText);
    status.textContent = t("version.copied");
  } catch {
    status.textContent = t("version.copyFailed");
  }
}

/**
 * Attach Copy version. Called once at startup.
 *
 * @returns Nothing.
 */
export function wireVersion(): void {
  el("copy-version").addEventListener("click", () => {
    void copyVersion();
  });
}
