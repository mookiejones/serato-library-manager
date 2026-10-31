/**
 * Every shortcut in the table, including the keys that must stay quiet.
 *
 * The cheat sheet is rendered from the same table. Space and the seek
 * keys call the registered player, and do nothing when it is absent.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import { el } from "./dom";
import { setLocale } from "./i18n";
import {
  chordLabel,
  chordMatches,
  registerPlayerControls,
  SEEK_SECONDS,
  SHORTCUTS,
  type ShortcutChord,
  type ShortcutId,
  repaintCheatSheet,
  wireShortcuts,
} from "./shortcuts";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList } from "./virtual-scroll";
import { renderFiles, renderList, wireLibrary } from "./views";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(input: RequestInfo | URL): Promise<Response> {
  const url = String(input);
  if (url.includes("/api/library-roots")) return Promise.resolve(json({ roots: [], computed_at: "t" }));
  if (url.includes("/api/files")) return Promise.resolve(json({ entries: [], path: "", parent: null, truncated: false }));
  if (url.includes("/api/snapshots")) return Promise.resolve(json({ snapshots: [] }));
  if (url.includes("/api/history")) return Promise.resolve(json({ sessions: [] }));
  if (url.includes("/api/track")) return Promise.resolve(json({ id: 1, name: "Alpha", artist: "Artist" }));
  return Promise.resolve(json({}));
}

const fetchMock = vi.fn(mockFetch);

function track(id: number, name: string): Track {
  return { id, name, artist: "Artist", album: "Album", file: `${name}.mp3` };
}

function press(init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  const target = document.activeElement instanceof HTMLElement ? document.activeElement : document.body;
  target.dispatchEvent(event);
  return event;
}

function covers(chord: ShortcutChord, init: KeyboardEventInit): boolean {
  const key = init.key ?? "";
  if (key !== chord.key && key.toLowerCase() !== chord.key.toLowerCase()) return false;
  const mod = Boolean(init.ctrlKey || init.metaKey);
  return mod === Boolean(chord.mod);
}

interface ShortcutCase {
  id: ShortcutId;
  event: KeyboardEventInit;
  prepare: () => void;
  ran: () => void;
  stayed: () => void;
}

function libraryRows(): void {
  state.mode = "crates";
  state.tracks = [track(1, "Alpha"), track(2, "Beta")];
  state.byId = new Map(state.tracks.map((item) => [item.id, item]));
  state.selectedId = 1;
  state.activeCrate = "all";
  renderList();
}

let toggles = 0;
let sought: number[] = [];

function usePlayer(): void {
  toggles = 0;
  sought = [];
  registerPlayerControls({
    togglePlayPause: () => {
      toggles += 1;
    },
    seekBy: (deltaSeconds: number) => {
      sought.push(deltaSeconds);
    },
  });
}

const cases: ShortcutCase[] = [
  {
    id: "focus-search",
    event: { key: "f", ctrlKey: true },
    prepare: () => {
      state.mode = "files";
      el("files-panel").hidden = false;
    },
    ran: () => expect(document.activeElement).toBe(el("files-search")),
    stayed: () => expect(document.activeElement).toBe(el("search")),
  },
  {
    id: "focus-search",
    event: { key: "f", metaKey: true },
    prepare: () => {
      state.mode = "files";
      el("files-panel").hidden = false;
    },
    ran: () => expect(document.activeElement).toBe(el("files-search")),
    stayed: () => expect(document.activeElement).toBe(el("search")),
  },
  {
    id: "focus-search",
    event: { key: "/" },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(document.activeElement).toBe(el("search")),
    stayed: () => expect(document.activeElement).toBe(el("crate-search")),
  },
  {
    id: "quick-open",
    event: { key: "k", ctrlKey: true },
    prepare: () => {
      document.body.focus();
    },
    ran: () => expect(el("quick-open").open).toBe(true),
    stayed: () => expect(el("quick-open").open).toBe(false),
  },
  {
    id: "quick-open",
    event: { key: "k", metaKey: true },
    prepare: () => {
      document.body.focus();
    },
    ran: () => expect(el("quick-open").open).toBe(true),
    stayed: () => expect(el("quick-open").open).toBe(false),
  },
  {
    id: "dismiss",
    event: { key: "Escape" },
    prepare: () => {
      el("search").value = "house";
      state.query = "house";
      document.body.focus();
    },
    ran: () => {
      expect(el("search").value).toBe("");
      expect(state.query).toBe("");
    },
    stayed: () => {
      expect(el("search").value).toBe("");
    },
  },
  {
    id: "cheat-sheet",
    event: { key: "?" },
    prepare: () => {
      document.body.focus();
    },
    ran: () => expect(el("shortcuts-dialog").open).toBe(true),
    stayed: () => expect(el("shortcuts-dialog").open).toBe(false),
  },
  {
    id: "list-previous",
    event: { key: "ArrowUp" },
    prepare: () => {
      libraryRows();
      state.selectedId = 2;
      document.body.focus();
    },
    ran: () => expect(state.selectedId).toBe(1),
    stayed: () => expect(state.selectedId).toBe(2),
  },
  {
    id: "list-next",
    event: { key: "ArrowDown" },
    prepare: () => {
      libraryRows();
      document.body.focus();
    },
    ran: () => expect(state.selectedId).toBe(2),
    stayed: () => expect(state.selectedId).toBe(1),
  },
  {
    id: "list-open",
    event: { key: "Enter" },
    prepare: () => {
      libraryRows();
      state.selectedId = 2;
      fetchMock.mockClear();
      document.body.focus();
    },
    ran: () => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes("/api/track?id=2"))).toBe(true);
    },
    stayed: () => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes("/api/track?id=2"))).toBe(false);
    },
  },
  {
    id: "play-pause",
    event: { key: " " },
    prepare: () => {
      usePlayer();
      document.body.focus();
    },
    ran: () => expect(toggles).toBe(1),
    stayed: () => expect(toggles).toBe(0),
  },
  {
    id: "seek-back",
    event: { key: "ArrowLeft" },
    prepare: () => {
      usePlayer();
      document.body.focus();
    },
    ran: () => expect(sought).toEqual([-SEEK_SECONDS]),
    stayed: () => expect(sought).toEqual([]),
  },
  {
    id: "seek-forward",
    event: { key: "ArrowRight" },
    prepare: () => {
      usePlayer();
      document.body.focus();
    },
    ran: () => expect(sought).toEqual([SEEK_SECONDS]),
    stayed: () => expect(sought).toEqual([]),
  },
  {
    id: "view-library",
    event: { key: "1", ctrlKey: true },
    prepare: () => {
      state.mode = "files";
      state.activeCrate = 4;
      document.body.focus();
    },
    ran: () => {
      expect(state.mode).toBe("crates");
      expect(state.activeCrate).toBe("all");
    },
    stayed: () => expect(state.mode).toBe("files"),
  },
  {
    id: "view-library",
    event: { key: "1", metaKey: true },
    prepare: () => {
      state.mode = "history";
      state.activeCrate = 4;
      document.body.focus();
    },
    ran: () => {
      expect(state.mode).toBe("crates");
      expect(state.activeCrate).toBe("all");
    },
    stayed: () => expect(state.mode).toBe("history"),
  },
  {
    id: "view-crates",
    event: { key: "2", ctrlKey: true },
    prepare: () => {
      state.mode = "files";
      document.body.focus();
    },
    ran: () => {
      expect(state.mode).toBe("crates");
      expect(document.activeElement).toBeInstanceOf(HTMLButtonElement);
      expect((document.activeElement as HTMLElement).classList.contains("crate")).toBe(true);
    },
    stayed: () => expect(state.mode).toBe("files"),
  },
  {
    id: "view-crates",
    event: { key: "2", metaKey: true },
    prepare: () => {
      state.mode = "files";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("crates"),
    stayed: () => expect(state.mode).toBe("files"),
  },
  {
    id: "view-files",
    event: { key: "3", ctrlKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("files"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
  {
    id: "view-files",
    event: { key: "3", metaKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("files"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
  {
    id: "view-history",
    event: { key: "4", ctrlKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("history"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
  {
    id: "view-history",
    event: { key: "4", metaKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("history"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
  {
    id: "view-snapshots",
    event: { key: "5", ctrlKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("snapshots"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
  {
    id: "view-snapshots",
    event: { key: "5", metaKey: true },
    prepare: () => {
      state.mode = "crates";
      document.body.focus();
    },
    ran: () => expect(state.mode).toBe("snapshots"),
    stayed: () => expect(state.mode).toBe("crates"),
  },
];

describe("keyboard shortcuts", () => {
  beforeEach(() => {
    installPage();
    mountTrackList();
    state.tracks = [];
    state.byId = new Map();
    state.crates = [];
    state.mode = "crates";
    state.activeCrate = "all";
    state.selectedId = null;
    state.query = "";
    state.crateQuery = "";
    state.view = [];
    state.filesEntries = [];
    state.filesSearching = false;
    state.filesAtRoots = false;
    state.filesActive = 0;
    state.filesSelected = new Set();
    state.historySessions = [];
    registerPlayerControls(null);
    fetchMock.mockReset();
    fetchMock.mockImplementation(mockFetch);
    vi.stubGlobal("fetch", fetchMock);
    wireLibrary();
    wireShortcuts();
  });

  it.each(cases.map((item) => [item.id, item.event.key, Boolean(item.event.metaKey), item] as const))(
    "%s (%s, command %s) runs",
    (_id, _key, _command, item) => {
      item.prepare();
      const event = press(item.event);
      item.ran();
      if (item.id === "play-pause" || item.id === "seek-back" || item.id === "seek-forward") {
        expect(event.defaultPrevented).toBe(true);
      }
    },
  );

  it.each(cases.map((item) => [item.id, item.event.key, Boolean(item.event.metaKey), item] as const))(
    "%s (%s, command %s) stays quiet while typing, except Esc",
    (_id, _key, _command, item) => {
      item.prepare();
      const shortcut = SHORTCUTS.find((row) => row.id === item.id);
      const field = item.id === "focus-search" && item.event.key === "/" ? el("crate-search") : el("search");
      field.focus();
      if (item.id !== "dismiss") field.value = "typing";
      press(item.event);
      if (shortcut?.whileTyping) item.ran();
      else item.stayed();
    },
  );

  it("covers every shortcut and both Control and Command", () => {
    const ids = new Set(cases.map((item) => item.id));
    expect(ids).toEqual(new Set(SHORTCUTS.map((shortcut) => shortcut.id)));
    expect(SHORTCUTS.filter((shortcut) => shortcut.whileTyping).map((shortcut) => shortcut.id)).toEqual(["dismiss"]);
    for (const shortcut of SHORTCUTS) {
      for (const chord of shortcut.keys) {
        const hits = cases.filter((item) => item.id === shortcut.id && covers(chord, item.event));
        expect(hits.length, shortcut.id).toBeGreaterThan(0);
        if (chord.mod) {
          expect(hits.some((item) => item.event.ctrlKey)).toBe(true);
          expect(hits.some((item) => item.event.metaKey)).toBe(true);
        }
      }
    }
  });

  it("draws the cheat sheet from the shortcut table", () => {
    el("open-shortcuts").click();
    const text = el("shortcuts-body").textContent ?? "";
    expect(el("shortcuts-dialog").open).toBe(true);
    expect(document.activeElement).toBe(el("shortcuts-title"));
    for (const shortcut of SHORTCUTS) {
      expect(text).toContain(shortcut.label);
      expect(text).toContain(shortcut.group);
      for (const chord of shortcut.keys) expect(text).toContain(chordLabel(chord));
    }
    expect(text).toContain("Ctrl/Cmd+K");
    expect(text).toContain("Ctrl/Cmd+1");
    press({ key: "Escape" });
    expect(el("shortcuts-dialog").open).toBe(false);
  });

  it("translates the open cheat sheet", () => {
    el("open-shortcuts").click();
    setLocale("es");
    try {
      repaintCheatSheet();
      expect(el("shortcuts-title").textContent).toBe("Atajos de teclado");
      expect(el("shortcuts-body").textContent).toContain("Enfocar la búsqueda");
      expect(el("shortcuts-body").textContent).not.toContain("Focus search");
    } finally {
      setLocale("en");
    }
  });

  it("does nothing for Space and the seek keys when no player is registered", () => {
    registerPlayerControls(null);
    document.body.focus();
    const space = press({ key: " " });
    const back = press({ key: "ArrowLeft" });
    const forward = press({ key: "ArrowRight" });
    expect(space.defaultPrevented).toBe(false);
    expect(back.defaultPrevented).toBe(false);
    expect(forward.defaultPrevented).toBe(false);
  });

  it("leaves Space on a button and ignores Alt chords", () => {
    usePlayer();
    el("open-settings").focus();
    press({ key: " " });
    el("rekordbox-memory").focus();
    press({ key: " " });
    expect(toggles).toBe(0);
    document.body.focus();
    press({ key: "k", altKey: true, ctrlKey: true });
    expect(el("quick-open").open).toBe(false);
    expect(chordMatches({ key: "k", mod: true }, new KeyboardEvent("keydown", { key: "k", altKey: true, ctrlKey: true }))).toBe(false);
  });

  it("moves and opens the file list from the keyboard", () => {
    state.mode = "files";
    state.filesAtRoots = false;
    state.filesEntries = [
      { name: "a.mp3", kind: "file", path: "/music/a.mp3" },
      { name: "b.mp3", kind: "file", path: "/music/b.mp3" },
    ];
    state.filesActive = 0;
    renderFiles();
    document.body.focus();
    press({ key: "ArrowDown" });
    expect(state.filesActive).toBe(1);
    press({ key: "Enter" });
    expect(state.filesSelected.has("/music/b.mp3")).toBe(true);
  });

  it("does not seek while the crate list is using the arrow keys", () => {
    usePlayer();
    state.tracks = [track(1, "Alpha")];
    renderList();
    const crate = el("crate-list").querySelector<HTMLButtonElement>(".crate");
    expect(crate).toBeTruthy();
    crate!.focus();
    crate!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true, cancelable: true }));
    expect(sought).toEqual([]);
  });

  it("closes quick-open on Esc and does not clear the search behind it", () => {
    el("search").value = "house";
    state.query = "house";
    document.body.focus();
    press({ key: "k", ctrlKey: true });
    el("quick-open-query").focus();
    press({ key: "Escape" });
    expect(el("quick-open").open).toBe(false);
    expect(el("search").value).toBe("house");
  });

  it("says when Snapshots has no search field", () => {
    state.mode = "snapshots";
    document.body.focus();
    press({ key: "/" });
    expect(el("snapshots-status").textContent).toContain("Ctrl+K");
  });
});
