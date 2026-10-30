/**
 * Quick-open finds loaded tracks immediately and files after the disk search.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { el } from "./dom";
import { parentDirectory, QUICK_OPEN_MS } from "./quick-open";
import { wireShortcuts } from "./shortcuts";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList } from "./virtual-scroll";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("parent folders", () => {
  it("keeps Windows and POSIX roots", () => {
    expect(parentDirectory("/Volumes/GIG/House/track.mp3")).toBe("/Volumes/GIG/House");
    expect(parentDirectory("/track.mp3")).toBe("/");
    expect(parentDirectory("C:\\Music\\House\\track.mp3")).toBe("C:\\Music\\House");
    expect(parentDirectory("C:\\track.mp3")).toBe("C:\\");
    expect(parentDirectory("\\\\server\\share\\track.mp3")).toBe("\\\\server\\share");
  });
});

describe("quick-open", () => {
  beforeEach(() => {
    installPage();
    mountTrackList();
    state.tracks = [
      { id: 7, name: "House Mix", artist: "Ada", album: "Night", file: "/music/house.mp3" },
      { id: 8, name: "Other", artist: "Bea", album: "Day", file: "/music/other.mp3" },
    ];
    state.byId = new Map(state.tracks.map((track) => [track.id, track]));
    state.mode = "crates";
    state.activeCrate = "all";
    state.selectedId = null;
    state.view = [];
    vi.useFakeTimers();
    wireShortcuts();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("lists a track immediately, then a file from the server, and opens the track", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/files")) {
        return Promise.resolve(json({
          search: true,
          query: "house",
          entries: [{ name: "House Mix.mp3", kind: "file", path: "/music/Deep/House Mix.mp3", detail: "/music/Deep", score: 10 }],
          truncated: false,
        }));
      }
      if (url.includes("/api/track")) return Promise.resolve(json({ id: 7, name: "House Mix", artist: "Ada" }));
      return Promise.resolve(json({ entries: [], roots: [], path: "/music/Deep", parent: "/music" }));
    });
    vi.stubGlobal("fetch", fetchMock);
    document.body.focus();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true, cancelable: true }));
    const field = el("quick-open-query");
    expect(el("quick-open").open).toBe(true);
    expect(document.activeElement).toBe(field);
    expect(el("quick-open-status").textContent).toContain("Type a track");
    field.value = "house";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    expect(el("quick-open-list").textContent).toContain("House Mix");
    expect(el("quick-open-list").textContent).toContain("Track");
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(QUICK_OPEN_MS);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/files?q=house");
    expect(el("quick-open-list").textContent).toContain("File");
    expect(el("quick-open-list").textContent).toContain("House Mix.mp3");
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    expect(document.getElementById("quick-open-option-1")?.getAttribute("aria-selected")).toBe("true");
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true, cancelable: true }));
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    expect(el("quick-open").open).toBe(false);
    expect(state.selectedId).toBe(7);
    expect(state.mode).toBe("crates");
  });

  it("keeps track matches when the file search fails, then says when nothing matches", async () => {
    let fail = true;
    const fetchMock = vi.fn(() => Promise.resolve(fail ? json({ error: "nope" }, 500) : json({ search: true, entries: [], truncated: false })));
    vi.stubGlobal("fetch", fetchMock);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true, cancelable: true }));
    const field = el("quick-open-query");
    field.value = "house";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(QUICK_OPEN_MS);
    expect(el("quick-open-status").textContent).toContain("could not be searched");
    expect(el("quick-open-list").textContent).toContain("House Mix");
    expect(el("quick-open-retry").hidden).toBe(false);
    fail = false;
    field.value = "zzzz";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(QUICK_OPEN_MS);
    expect(el("quick-open-status").textContent).toContain("No tracks or files match");
  });
});
