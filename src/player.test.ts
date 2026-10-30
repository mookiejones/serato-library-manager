/**
 * Player API, the row play control, and the Space binding.
 *
 * A fake media element stands in for <audio> so the tests do not fetch.
 * The library is not opened.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import {
  attachMedia,
  bindSpaceToggle,
  formatPlayerTime,
  getPlayerState,
  isPlaying,
  isTypingTarget,
  mountPlayer,
  pause,
  play,
  seek,
  seekBy,
  subscribe,
  togglePlayPause,
  type PlayableMedia,
} from "./player";
import { playerStrings } from "./player-strings";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList, paintRows } from "./virtual-scroll";

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
    expect(document.querySelector(".player-toggle")?.textContent).toBe(playerStrings.pause);

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

  it("shows a plain message when the file cannot play", () => {
    state.byId.set(4, track(4, "Night"));
    play(4);
    fake.dispatchEvent(new Event("error"));
    expect(isPlaying()).toBe(false);
    expect(document.querySelector(".player-status")?.textContent).toBe(playerStrings.cannotPlay);
  });

  it("does nothing from toggle when no track is loaded", () => {
    togglePlayPause();
    expect(isPlaying()).toBe(false);
    expect(fake.src).toBe("");
  });
});

describe("Space", () => {
  it("toggles playback and ignores typing targets", () => {
    state.byId.set(4, track(4, "Night"));
    play(4);
    const stop = bindSpaceToggle();
    const input = document.createElement("input");
    const area = document.createElement("textarea");
    const editor = document.createElement("div");
    editor.contentEditable = "true";
    document.body.append(input, area, editor);
    expect(isTypingTarget(input)).toBe(true);
    expect(isTypingTarget(area)).toBe(true);
    expect(isTypingTarget(editor)).toBe(true);

    for (const target of [input, area, editor]) {
      target.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
      expect(isPlaying()).toBe(true);
    }

    const plain = document.createElement("div");
    document.body.append(plain);
    const event = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
    plain.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(isPlaying()).toBe(false);
    stop();
  });

  it("plays the selected track when nothing is loaded", () => {
    state.byId.set(8, track(8, "Dawn"));
    state.selectedId = 8;
    const stop = bindSpaceToggle();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
    expect(isPlaying()).toBe(true);
    expect(fake.src).toContain("id=8");
    stop();
  });

  it("leaves Space to a focused button", () => {
    state.byId.set(4, track(4, "Night"));
    play(4);
    const stop = bindSpaceToggle();
    const button = document.createElement("button");
    document.body.append(button);
    button.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
    expect(isPlaying()).toBe(true);
    stop();
  });
});

describe("track rows", () => {
  beforeEach(() => {
    mountTrackList();
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
