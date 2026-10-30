/**
 * Player API, the row play control, and the Space binding.
 *
 * A fake media element stands in for <audio> so the tests do not fetch.
 * The library is not opened.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import {
  SEEK_STEP_LARGE_SECONDS,
  SEEK_STEP_SECONDS,
  attachMedia,
  formatPlayerTime,
  getPlayerState,
  isPlaying,
  markersFromCues,
  mountPlayer,
  next,
  pause,
  play,
  playbackErrorText,
  playerControls,
  previous,
  seek,
  seekBy,
  subscribe,
  togglePlayPause,
  type PlayableMedia,
} from "./player";
import { playerStrings } from "./player-strings";
import { registerPlayerControls, wireShortcuts } from "./shortcuts";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList, paintRows, wireVirtualScroll } from "./virtual-scroll";

class FakeAudio extends EventTarget implements PlayableMedia {
  src = "";
  currentTime = 0;
  duration = 0;
  volume = 1;
  paused = true;
  play(): Promise<void> {
    this.paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  }
  pause(): void {
    this.paused = true;
    this.dispatchEvent(new Event("pause"));
  }
}

let fake: FakeAudio;

function track(id: number, name: string, artist = "DJ"): Track {
  return { id, name, artist };
}

beforeEach(() => {
  installPage();
  fake = new FakeAudio();
  attachMedia(fake);
  mountPlayer();
  state.space = "Serato Library";
  state.mode = "crates";
  state.selectedId = null;
  state.byId = new Map();
  state.view = [];
  state.tracks = [];
});

describe("formatPlayerTime", () => {
  it("formats minutes and hours and treats a bad number as zero", () => {
    expect(formatPlayerTime(0)).toBe("0:00");
    expect(formatPlayerTime(65)).toBe("1:05");
    expect(formatPlayerTime(3723)).toBe("1:02:03");
    expect(formatPlayerTime(Number.NaN)).toBe("0:00");
  });
});

describe("player API", () => {
  it("plays, pauses, toggles, and reports playing", () => {
    state.byId.set(4, track(4, "Night", "Ada"));
    expect(isPlaying()).toBe(false);
    play(4);
    expect(isPlaying()).toBe(true);
    expect(fake.src).toContain("/api/audio?");
    expect(fake.src).toContain("id=4");
    expect(fake.src).not.toContain("path=");
    expect(fake.src).toContain("space=Serato+Library");
    expect(getPlayerState().title).toBe("Night");
    expect(getPlayerState().artist).toBe("Ada");
    expect(document.querySelector(".player-title")?.textContent).toBe("Night");
    expect(document.querySelector(".player-play")?.textContent).toBe(playerStrings.pause);

    pause();
    expect(isPlaying()).toBe(false);
    expect(fake.paused).toBe(true);

    togglePlayPause();
    expect(isPlaying()).toBe(true);
    togglePlayPause();
    expect(isPlaying()).toBe(false);
  });

  it("seeks to a position and by a delta, clamped to the duration", () => {
    state.byId.set(4, track(4, "Night"));
    fake.duration = 20;
    play(4);
    seek(5);
    expect(fake.currentTime).toBe(5);
    seekBy(3);
    expect(fake.currentTime).toBe(8);
    seekBy(-2);
    expect(fake.currentTime).toBe(6);
    seek(50);
    expect(fake.currentTime).toBe(20);
    seek(-4);
    expect(fake.currentTime).toBe(0);
    seek(Number.NaN);
    expect(fake.currentTime).toBe(0);
  });

  it("notifies a subscriber and stops after unsubscribe", () => {
    state.byId.set(4, track(4, "Night"));
    const seen: boolean[] = [];
    const stop = subscribe((snapshot) => {
      seen.push(snapshot.playing);
    });
    play(4);
    expect(seen.at(-1)).toBe(true);
    stop();
    const count = seen.length;
    pause();
    expect(seen.length).toBe(count);
  });

  it("sets the volume from the slider without treating zero as missing", () => {
    const input = document.querySelector<HTMLInputElement>(".player-volume input");
    expect(input).not.toBeNull();
    input!.value = "0";
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    expect(fake.volume).toBe(0);
    expect(getPlayerState().volume).toBe(0);
  });

  it("shows the window message when the file cannot be decoded", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(null, { status: 415 })));
    state.byId.set(4, track(4, "Night"));
    play(4);
    fake.dispatchEvent(new Event("error"));
    await vi.waitUntil(() => document.querySelector(".player-status")?.textContent === playerStrings.cannotPlay);
    expect(isPlaying()).toBe(false);
    expect(document.querySelector(".player-status")?.getAttribute("title")).toBe(playerStrings.cannotPlay);
  });

  it("plays the selected track from toggle when nothing is loaded", () => {
    state.byId.set(8, track(8, "Dawn"));
    state.selectedId = 8;
    state.view = [track(8, "Dawn")];
    togglePlayPause();
    expect(isPlaying()).toBe(true);
    expect(fake.src).toContain("id=8");
    expect(document.querySelector(".player-play")?.getAttribute("aria-label")).toBe("Pause Dawn");
  });

  it("does nothing from toggle when nothing is selected", () => {
    togglePlayPause();
    expect(isPlaying()).toBe(false);
    expect(fake.src).toBe("");
  });

  it("names the play button for the loaded state", () => {
    state.byId.set(4, track(4, "Night"));
    play(4);
    expect(document.querySelector(".player-play")?.getAttribute("aria-label")).toBe("Pause Night");
    pause();
    expect(document.querySelector(".player-play")?.getAttribute("aria-label")).toBe("Play Night");
    expect(document.querySelector(".player-play")?.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("playback errors", () => {
  it("maps 403 and 404 to the library message and leaves other statuses", () => {
    expect(playbackErrorText(404)).toBe(playerStrings.notInLibrary);
    expect(playbackErrorText(403)).toBe(playerStrings.notInLibrary);
    expect(playbackErrorText(415)).toBe(playerStrings.cannotPlay);
    expect(playbackErrorText(0)).toBe(playerStrings.cannotPlay);
  });

  it("shows the library message when the audio request is refused", async () => {
    vi.stubGlobal("fetch", (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "HEAD") return Promise.resolve(new Response(null, { status: 404 }));
      return Promise.resolve(new Response(JSON.stringify({ cues: [] }), { status: 200 }));
    });
    state.byId.set(4, track(4, "Night"));
    play(4);
    fake.dispatchEvent(new Event("error"));
    await vi.waitUntil(() => document.querySelector(".player-status")?.textContent === playerStrings.notInLibrary);
    const status = document.querySelector(".player-status");
    expect(status?.getAttribute("title")).toBe(playerStrings.notInLibrary);
    expect(status?.textContent).toBe("Not in the library or file missing");
  });
});

describe("next and previous", () => {
  const rows = [track(3, "C"), track(1, "A"), track(2, "B")];

  beforeEach(() => {
    state.view = rows;
    for (const row of rows) state.byId.set(row.id, row);
  });

  it("walks the visible list in its sort order", () => {
    play(3);
    next();
    expect(fake.src).toContain("id=1");
    next();
    expect(fake.src).toContain("id=2");
    next();
    expect(fake.src).toContain("id=2");
    previous();
    expect(fake.src).toContain("id=1");
    expect(isPlaying()).toBe(true);
  });

  it("starts the next visible track when the current one ends", () => {
    play(1);
    fake.dispatchEvent(new Event("ended"));
    expect(fake.src).toContain("id=2");
    expect(isPlaying()).toBe(true);
    fake.dispatchEvent(new Event("ended"));
    expect(fake.src).toContain("id=2");
    expect(isPlaying()).toBe(false);
  });

  it("skips a history row and stays inside the filtered list", () => {
    state.view = [track(5, "Keep"), { id: 6, name: "Old", entry: true }, track(9, "Also")];
    state.byId.set(5, track(5, "Keep"));
    state.byId.set(9, track(9, "Also"));
    play(5);
    next();
    expect(fake.src).toContain("id=9");
    previous();
    expect(fake.src).toContain("id=5");
  });

  it("exposes the same functions the shortcut table registers", () => {
    expect(playerControls.togglePlayPause).toBe(togglePlayPause);
    expect(playerControls.seekBy).toBe(seekBy);
    expect(SEEK_STEP_SECONDS).toBe(5);
    expect(SEEK_STEP_LARGE_SECONDS).toBe(30);
  });
});

describe("shortcut table", () => {
  it("toggles play and pause once from Space and seeks 5 seconds from the arrows", () => {
    registerPlayerControls(playerControls);
    wireShortcuts();
    state.byId.set(4, track(4, "Night"));
    state.selectedId = 4;
    state.view = [track(4, "Night")];
    const space = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
    document.body.dispatchEvent(space);
    expect(space.defaultPrevented).toBe(true);
    expect(isPlaying()).toBe(true);
    expect(fake.src).toContain("id=4");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
    expect(isPlaying()).toBe(false);

    fake.duration = 100;
    play(4);
    fake.dispatchEvent(new Event("durationchange"));
    seek(10);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
    expect(fake.currentTime).toBe(15);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true, cancelable: true }));
    expect(fake.currentTime).toBe(10);

    const range = document.querySelector<HTMLInputElement>(".player-range");
    range!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
    expect(fake.currentTime).toBe(15);
  });
});

describe("seek keys", () => {
  it("moves 5 seconds, and 30 with Shift, without bubbling", () => {
    state.byId.set(4, track(4, "Night"));
    fake.duration = 100;
    play(4);
    fake.dispatchEvent(new Event("durationchange"));
    seek(10);
    const range = document.querySelector<HTMLInputElement>(".player-range");
    expect(range).not.toBeNull();
    let bubbled = false;
    const hear = () => {
      bubbled = true;
    };
    document.addEventListener("keydown", hear);
    const forward = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
    range!.dispatchEvent(forward);
    expect(forward.defaultPrevented).toBe(true);
    expect(bubbled).toBe(false);
    expect(fake.currentTime).toBe(15);
    range!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", shiftKey: true, bubbles: true, cancelable: true }));
    expect(fake.currentTime).toBe(45);
    range!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true, cancelable: true }));
    expect(fake.currentTime).toBe(40);
    document.removeEventListener("keydown", hear);
  });
});

describe("cue markers", () => {
  it("drops a cue that has no time and names the rest", () => {
    expect(markersFromCues(undefined)).toEqual([]);
    expect(markersFromCues([])).toEqual([]);
    expect(markersFromCues([
      { start_ms: 1500, color: "#CC0000", name: "Drop", index: 0 },
      { start_ms: "nope", name: "Skip" },
      { start_ms: 8000, color: "red", index: 3 },
    ])).toEqual([
      { seconds: 1.5, color: "#CC0000", label: "Drop" },
      { seconds: 8, color: "", label: "Cue 4" },
    ]);
  });

  it("draws markers from the track and seeks when one is clicked", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({
      cues: [
        { index: 0, start_ms: 1500, color: "#CC0000", name: "Drop" },
        { index: 3, start_ms: 8000, color: "#001122", name: "" },
      ],
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
    state.byId.set(4, track(4, "Night"));
    fake.duration = 10;
    play(4);
    fake.dispatchEvent(new Event("durationchange"));
    await vi.waitUntil(() => document.querySelectorAll(".player-cue").length === 2);
    const marks = [...document.querySelectorAll<HTMLButtonElement>(".player-cue")];
    expect(marks[0]?.style.getPropertyValue("--cue")).toBe("#CC0000");
    expect(marks[0]?.getAttribute("aria-label")).toBe("Drop, 0:01");
    expect(marks[0]?.style.left).toBe("15%");
    expect(marks[1]?.getAttribute("aria-label")).toBe("Cue 4, 0:08");
    marks[0]?.click();
    expect(fake.currentTime).toBe(1.5);
    expect(isPlaying()).toBe(true);
  });

  it("draws no markers when the track has no cues", async () => {
    const body = Promise.resolve(new Response(JSON.stringify({ cues: [] }), { status: 200 }));
    vi.stubGlobal("fetch", () => body);
    state.byId.set(4, track(4, "Night"));
    fake.duration = 10;
    play(4);
    fake.dispatchEvent(new Event("durationchange"));
    await body;
    await Promise.resolve();
    await Promise.resolve();
    expect(document.querySelectorAll(".player-cue")).toHaveLength(0);
  });
});

describe("track rows", () => {
  beforeEach(() => {
    mountTrackList();
  });

  it("plays the focused row on Enter, and the selected row when the list is focused", () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({ cues: [] }), { status: 200 })));
    wireVirtualScroll();
    const first = track(4, "Night", "Ada");
    const second = track(5, "Dawn", "Ada");
    state.view = [first, second];
    state.byId.set(4, first);
    state.byId.set(5, second);
    state.selectedId = 4;
    paintRows();
    const list = document.getElementById("list");
    list?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    expect(fake.src).toContain("id=4");

    pause();
    const rows = document.querySelectorAll<HTMLElement>(".row");
    rows[1]?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    expect(fake.src).toContain("id=5");
    expect(isPlaying()).toBe(true);
  });

  it("plays from the row button and from a double-click", () => {
    const row = track(4, "Night", "Ada");
    state.view = [row];
    state.byId.set(4, row);
    paintRows();
    const playButton = document.querySelector<HTMLButtonElement>(".row-play");
    expect(playButton?.getAttribute("aria-label")).toBe("Play Night");
    playButton?.click();
    expect(fake.src).toContain("id=4");
    expect(isPlaying()).toBe(true);

    pause();
    const painted = document.querySelector<HTMLElement>(".row");
    painted?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    expect(isPlaying()).toBe(true);
  });

  it("does not offer play on a history row", () => {
    state.view = [{ id: 3, name: "Old", entry: true }];
    state.mode = "history";
    paintRows();
    expect(document.querySelector(".row-play")).toBeNull();
  });
});

describe("detail play", () => {
  it("starts the open track from the detail button", async () => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/track")) {
        return Promise.resolve(new Response(JSON.stringify({
          id: 4,
          title: "Night",
          artist: "Ada",
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return Promise.reject(new Error(url));
    });
    const { selectTrack } = await import("./views");
    await selectTrack(4);
    const button = document.querySelector<HTMLButtonElement>(".detail-play");
    expect(button?.textContent).toBe(playerStrings.play);
    expect(button?.getAttribute("aria-label")).toBe("Play Night");
    button?.click();
    expect(fake.src).toContain("id=4");
    expect(isPlaying()).toBe(true);
  });
});
