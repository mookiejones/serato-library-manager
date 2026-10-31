/**
 * Mount the page tooltips and a sample of the dynamic controls.
 *
 * The spec loads index.html first. This bundle does not open a window
 * and does not read a Serato library. Fetch answers the detail request
 * so related tracks and the editor are on the page for the audit.
 */

import { mountPlayer } from "../src/player";
import { state } from "../src/state";
import { applyStaticTooltips, installTooltips, missingTooltipLabels } from "../src/tooltip";
import { mountTrackList, paintRows } from "../src/virtual-scroll";
import { renderCrates, renderFiles, renderSessions, selectTrack } from "../src/views";

declare global {
  interface Window {
    tooltipAudit: { missing: () => string[] };
  }
}

const track = {
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

window.fetch = (input: RequestInfo | URL) => {
  const url = String(input);
  const body = url.includes("/api/related")
    ? {
      saved: [{ mutual: true, track: { title: "Alpha", artist: "Bea", asset_id: 2, in_library: true } }],
      suggested: [{ title: "Beta", artist: "Cy", asset_id: 3, reasons: ["same key"] }],
      crate_name: "Related - Night",
    }
    : url.includes("/api/track")
      ? track
      : {};
  return Promise.resolve(new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
};

state.rootId = 1;
state.writable = true;
state.serato = { writable: true, file_manager: "Finder", message: "Serato is quit." };
state.mode = "crates";
state.selectedId = 1;
state.duplicateGroups = [{ ids: [1, 2] }];
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
state.tracks = [
  { id: 1, name: "Night", artist: "Ada" },
  { id: 2, name: "Alpha", artist: "Bea" },
];
state.byId = new Map(state.tracks.map((row) => [row.id, row]));
state.view = [{ id: 1, name: "Night", artist: "Ada" }];
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

applyStaticTooltips();
installTooltips();
mountPlayer();
mountTrackList();
state.mode = "files";
renderFiles();
state.mode = "crates";
renderCrates();
renderSessions();
paintRows();
state.mode = "duplicates";

void selectTrack(1).then(async () => {
  const started = Date.now();
  while (!document.querySelector("[data-related-crate]") && Date.now() - started < 2000) {
    await new Promise((resolve) => window.setTimeout(resolve, 10));
  }
  const search = document.querySelector<HTMLInputElement>(".related-search input");
  if (search) {
    search.value = "Alpha";
    search.dispatchEvent(new Event("input", { bubbles: true }));
  }
  document.querySelector<HTMLButtonElement>(".related-results button")?.click();
  window.tooltipAudit = { missing: () => missingTooltipLabels() };
  document.body.dataset.tooltips = "ready";
}).catch(() => {
  document.body.dataset.tooltips = "failed";
});
