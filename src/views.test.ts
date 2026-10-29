import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList } from "./virtual-scroll";
import { renderCrates, renderFiles, renderList, renderSessions } from "./views";

vi.hoisted(() => {
  vi.stubGlobal("fetch", () => {
    throw new Error("view tests do not fetch");
  });
});

function track(id: number, fields: Partial<Track> = {}): Track {
  return { id, name: `Track ${id}`, artist: "Artist", album: "Album", file: `${id}.mp3`, ...fields };
}

function titles(): string[] {
  return [...document.querySelectorAll<HTMLElement>("#list .title")].map((node) => node.textContent ?? "");
}

function resetState(): void {
  state.tracks = [];
  state.byId = new Map();
  state.crates = [];
  state.crateTracks = new Map();
  state.rootId = null;
  state.activeCrate = "all";
  state.query = "";
  state.crateQuery = "";
  state.crateSort = "order";
  state.sort = "name";
  state.sortDir = 1;
  state.selectedId = null;
  state.request = 0;
  state.expanded = new Set();
  state.space = "Serato Library";
  state.mode = "crates";
  state.writable = false;
  state.serato = null;
  state.historySessions = [];
  state.historyId = null;
  state.entries = [];
  state.duplicateIds = null;
  state.duplicateGroups = [];
  state.duplicateSpace = "";
  state.filesPath = "";
  state.filesParent = null;
  state.filesEntries = [];
  state.filesSelected = new Set();
  state.filesPick = null;
  state.filesPickPaths = [];
  state.filesPickSource = "";
  state.filesLoading = false;
  state.filesError = "";
  state.filesMessage = "";
  state.filesTruncated = false;
  state.view = [];
}

describe("library views", () => {
  beforeEach(() => {
    installPage();
    mountTrackList();
    resetState();
  });

  it("paints the crate tree, keeps a matching child's parent, and counts the track search", () => {
    state.rootId = 1;
    state.tracks = [track(1, { name: "Alpha" }), track(2, { name: "Beta" })];
    state.crates = [
      { id: 2, name: "House", parent: 1, order: 0, color: 0xcc0000 },
      { id: 3, name: "Deep", parent: 2, order: 0, smart: true },
    ];
    state.crateTracks = new Map([[2, new Set([1])], [3, new Set([1, 2])]]);
    state.expanded = new Set([2]);
    state.selectedId = 1;
    renderList();

    const names = [...document.querySelectorAll<HTMLElement>("#crate-list .name")].map((node) => node.textContent ?? "");
    expect(names).toEqual(["All tracks", "House", "Deep"]);
    expect(document.querySelector("#crate-list .swatch")).not.toBeNull();
    expect(document.querySelector("#crate-list .smart")?.textContent).toBe("smart");
    const deep = [...document.querySelectorAll<HTMLElement>("#crate-list .crate-row")]
      .find((row) => row.textContent?.includes("Deep"));
    expect(deep?.style.paddingLeft).toBe("14px");

    state.expanded = new Set();
    state.crateQuery = "deep";
    renderCrates();
    const filtered = [...document.querySelectorAll<HTMLElement>("#crate-list .name")].map((node) => node.textContent ?? "");
    expect(filtered).toEqual(["All tracks", "House", "Deep"]);

    state.crateQuery = "";
    state.query = "alpha";
    state.expanded = new Set([2]);
    renderCrates();
    const counts = [...document.querySelectorAll<HTMLElement>("#crate-list .meta")].map((node) => node.textContent ?? "");
    expect(counts).toEqual(["1", "1", "1"]);
  });

  it("lists history sessions and paints deck, played, and the history columns", () => {
    state.mode = "history";
    state.sort = "start";
    state.sortDir = -1;
    state.historyId = 4;
    state.historySessions = [{ id: 4, name: "Friday", played: 3 }];
    state.entries = [{
      id: 9,
      name: "Alpha",
      artist: "Artist",
      file: "a.mp3",
      deck: "1",
      played: "Yes",
      start_time: 100,
      length_ms: 180000,
      asset_id: 1,
    } as Track];
    state.selectedId = 9;
    renderSessions();
    renderList();

    const session = document.querySelector("#session-list .crate");
    expect(session?.textContent).toContain("Friday");
    expect(session?.textContent).toContain("3");
    expect(session?.getAttribute("aria-selected")).toBe("true");
    const columns = [...document.querySelectorAll<HTMLButtonElement>(".columns button")].map((button) => button.textContent);
    expect(columns).toEqual(["Title", "Artist", "Deck", "Played", "Time"]);
    expect(titles()).toEqual(["Alpha"]);
    expect(document.querySelector("#list .row")?.textContent).toContain("Yes");
    expect(document.querySelector("#count")?.textContent).toBe("1 play");
  });

  it("shows missing tracks and the missing note", () => {
    state.mode = "missing";
    state.tracks = [track(1, { name: "Gone", missing: true }), track(2, { name: "Here" })];
    state.selectedId = 1;
    renderList();
    expect(titles()).toEqual(["Gone"]);
    expect(document.querySelector("#list .missing-word")?.textContent).toBe("missing");
    expect(document.querySelector("#mode-note")?.textContent).toBe("Tracks Serato has marked missing in this space.");
    expect((document.querySelector("#mode-note") as HTMLElement).hidden).toBe(false);
  });

  it("waits for duplicate ids, then lists the group and enables merge when Serato is quit", () => {
    state.mode = "duplicates";
    state.tracks = [track(1, { name: "Only" }), track(2, { name: "Copy" })];
    state.duplicateIds = null;
    renderList();
    expect(document.querySelector("#list .empty-list")?.textContent).toBe("Reading duplicates");
    expect((document.querySelector("#duplicate-actions") as HTMLElement).hidden).toBe(false);
    expect((document.querySelector("#merge-duplicates") as HTMLButtonElement).disabled).toBe(true);

    state.duplicateIds = new Set([2]);
    state.duplicateGroups = [{ ids: [2, 8] }];
    state.selectedId = 2;
    state.writable = true;
    renderList();
    expect(titles()).toEqual(["Copy"]);
    expect((document.querySelector("#merge-duplicates") as HTMLButtonElement).disabled).toBe(false);
    expect(document.querySelector("#mode-note")?.textContent).toContain("merge the others into it");
  });

  it("shows tracks that have a stems analysis", () => {
    state.mode = "stems";
    state.tracks = [track(1, { name: "Stemmed", stems: true }), track(2, { name: "Plain" })];
    state.selectedId = 1;
    renderList();
    expect(titles()).toEqual(["Stemmed"]);
    expect(document.querySelector("#list .missing-word")?.textContent).toBe("stems");
    expect(document.querySelector("#mode-note")?.textContent).toBe("Tracks with a stems analysis state.");
  });

  it("paints a folder, an empty folder, and a folder that is still loading", () => {
    state.mode = "files";
    state.writable = true;
    state.filesPath = "/music";
    state.filesParent = "/";
    state.filesEntries = [
      { name: "Crates", kind: "dir", path: "/music/Crates" },
      { name: "a.mp3", kind: "file", path: "/music/a.mp3", in_library: true },
      { name: "alias", kind: "link", path: "/music/alias" },
    ];
    renderFiles();
    const text = document.querySelector("#files-list")?.textContent ?? "";
    expect(text).toContain("Crates");
    expect(text).toContain("a.mp3");
    expect(text).toContain("In library");
    expect(text).toContain("alias (shortcut)");
    expect(document.querySelector("#files-path")?.textContent).toBe("/music");
    expect((document.querySelector("#files-rename") as HTMLButtonElement).disabled).toBe(true);
    expect(document.querySelector("#mode-note")?.textContent).toContain("Files on disk");

    state.filesSelected = new Set(["/music/a.mp3"]);
    renderFiles();
    expect((document.querySelector("#files-rename") as HTMLButtonElement).disabled).toBe(false);

    state.filesEntries = [];
    state.filesSelected = new Set();
    state.filesLoading = false;
    renderFiles();
    expect(document.querySelector("#files-list .files-empty")?.textContent).toBe("This folder is empty.");

    state.filesLoading = true;
    renderFiles();
    expect(document.querySelector("#files-list .files-empty")?.textContent).toBe("Reading this folder.");
    expect(document.querySelector("#files-status")?.textContent).toContain("Reading this folder.");
  });
});
