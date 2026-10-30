/**
 * Waveform controls: zoom, overview seek, Serato-then-computed, and a missing file.
 *
 * Fetch is stubbed. The audio element is not used. No shortcut is added.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { playerStrings } from "./player-strings";
import { SHORTCUTS } from "./shortcuts";
import { state } from "./state";
import { mountWaveform, type WaveformHooks } from "./waveform-view";
import { ZOOM_MAX_PPS, type ParsedWaveform } from "./waveform";

function hooks(seek: (seconds: number) => void = () => {}, seekBy: (delta: number) => void = () => {}): WaveformHooks {
  return {
    seek,
    seekBy,
    getTime: () => 0,
    getDuration: () => 20,
    getPlaying: () => false,
    formatTime: (seconds) => `${seconds}`,
    seekStep: 5,
    seekStepLarge: 30,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function parsedWave(): ParsedWaveform {
  return {
    version: 1,
    flags: 3,
    analyzerVersion: 1,
    sampleRate: 44100,
    pointsPerSecond: 150,
    durationMs: 20_000,
    detail: new Uint8Array(6),
    overview: new Uint8Array([180, 180, 0, 0, 0, 0]),
    serato: new Uint8Array(),
    detailCount: 1,
    overviewCount: 1,
    seratoColumns: 0,
    seratoBands: 0,
    lowHz: 250,
    highHz: 4000,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("waveform controls", () => {
  it("zooms from the buttons and from Ctrl or Command with the wheel, not from keys", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, hooks());
    view.showComputed(parsedWave());
    const zoomIn = host.querySelector<HTMLButtonElement>("[aria-label='Zoom in']");
    const zoomOut = host.querySelector<HTMLButtonElement>("[aria-label='Zoom out']");
    expect(zoomIn?.title).toBe(playerStrings.zoomIn);
    expect(zoomOut?.title).toBe(playerStrings.zoomOut);
    expect(host.querySelector(".waveform-overview")?.getAttribute("title")).toBe(playerStrings.overviewSeek);
    expect(view.pixelsPerSecond()).toBe(80);
    zoomIn?.click();
    expect(view.pixelsPerSecond()).toBe(100);
    const wheel = new WheelEvent("wheel", { deltaY: -40, ctrlKey: true, cancelable: true });
    host.dispatchEvent(wheel);
    expect(wheel.defaultPrevented).toBe(true);
    expect(view.pixelsPerSecond()).toBe(125);
    const plain = new WheelEvent("wheel", { deltaY: -40, cancelable: true });
    host.dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
    expect(view.pixelsPerSecond()).toBe(125);
    const command = new WheelEvent("wheel", { deltaY: 40, metaKey: true, cancelable: true });
    host.dispatchEvent(command);
    expect(view.pixelsPerSecond()).toBe(100);
    const before = view.pixelsPerSecond();
    for (const key of ["+", "-", "=", "Equal"]) {
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      host.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    expect(view.pixelsPerSecond()).toBe(before);
    zoomOut?.click();
    expect(view.pixelsPerSecond()).toBe(80);
  });

  it("stops at the zoom limits", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, hooks());
    view.showComputed(parsedWave());
    const zoomIn = host.querySelector<HTMLButtonElement>("[aria-label='Zoom in']");
    const zoomOut = host.querySelector<HTMLButtonElement>("[aria-label='Zoom out']");
    expect(zoomIn).not.toBeNull();
    expect(zoomOut).not.toBeNull();
    for (let step = 0; step < 12 && !zoomIn!.disabled; step += 1) zoomIn!.click();
    expect(view.pixelsPerSecond()).toBe(ZOOM_MAX_PPS);
    expect(zoomIn!.disabled).toBe(true);
    zoomIn!.click();
    expect(view.pixelsPerSecond()).toBe(ZOOM_MAX_PPS);
    for (let step = 0; step < 20 && !zoomOut!.disabled; step += 1) zoomOut!.click();
    expect(view.pixelsPerSecond()).toBe(10);
    expect(zoomOut!.disabled).toBe(true);
  });

  it("seeks from a click and a drag on the overview", () => {
    const seen: number[] = [];
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, hooks((seconds) => seen.push(seconds)));
    view.showComputed(parsedWave());
    const overview = host.querySelector<HTMLElement>(".waveform-overview");
    expect(overview).not.toBeNull();
    overview!.getBoundingClientRect = () =>
      ({
        left: 10,
        width: 200,
        top: 0,
        height: 36,
        right: 210,
        bottom: 36,
        x: 10,
        y: 0,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    overview!.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: 60, bubbles: true }));
    overview!.dispatchEvent(new PointerEvent("pointermove", { clientX: 110, bubbles: true }));
    overview!.dispatchEvent(new PointerEvent("pointerup", { clientX: 110, bubbles: true }));
    expect(seen).toEqual([5, 10]);
    overview!.dispatchEvent(new PointerEvent("pointermove", { clientX: 160, bubbles: true }));
    expect(seen).toEqual([5, 10]);
  });

  it("leaves the shortcut table unchanged", () => {
    expect(SHORTCUTS.map((shortcut) => shortcut.id)).toEqual([
      "focus-search",
      "quick-open",
      "dismiss",
      "cheat-sheet",
      "list-previous",
      "list-next",
      "list-open",
      "play-pause",
      "seek-back",
      "seek-forward",
      "view-library",
      "view-crates",
      "view-files",
      "view-history",
      "view-snapshots",
    ]);
    const play = SHORTCUTS.find((shortcut) => shortcut.id === "play-pause");
    const back = SHORTCUTS.find((shortcut) => shortcut.id === "seek-back");
    const forward = SHORTCUTS.find((shortcut) => shortcut.id === "seek-forward");
    expect(play?.keys).toEqual([{ key: " " }]);
    expect(back?.keys).toEqual([{ key: "ArrowLeft" }]);
    expect(forward?.keys).toEqual([{ key: "ArrowRight" }]);
  });
});

describe("waveform loading", () => {
  it("shows Serato Overview before the computed waveform replaces it", async () => {
    let release: (response: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const calls: string[] = [];
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("/api/waveform/overview")) {
        const column = new Array(16).fill(0);
        column[0] = 200;
        return Promise.resolve(json({ available: true, columns: 1, bands: 16, data: [column] }));
      }
      if (url.includes("/api/waveform")) return gate;
      return Promise.reject(new Error(url));
    });
    state.space = "Serato Library";
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, hooks());
    view.setTrack(7);
    expect(host.querySelector<HTMLButtonElement>("[aria-label='Zoom in']")?.disabled).toBe(true);
    expect(host.querySelector<HTMLButtonElement>("[aria-label='Zoom out']")?.disabled).toBe(true);
    await vi.waitUntil(() => host.querySelector(".waveform-overview")?.getAttribute("data-waveform-overview") === "serato");
    expect(host.dataset.waveformState).toBe("reading");
    expect(calls.some((url) => url.includes("/api/waveform?") && !url.includes("overview") && !url.includes("path="))).toBe(true);
    const body = new Uint8Array(64);
    body.set([0x53, 0x57, 0x46, 0x31], 0);
    const bytes = parsedBody();
    const copy = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(copy).set(bytes);
    release(new Response(copy, { status: 200, headers: { "Content-Type": "application/octet-stream" } }));
    await vi.waitUntil(() => host.querySelector(".waveform-overview")?.getAttribute("data-waveform-overview") === "computed");
    expect(host.dataset.waveformState).toBe("ready");
    expect(host.querySelector<HTMLElement>(".waveform-note")?.hidden).toBe(true);
    expect(host.querySelector<HTMLButtonElement>("[aria-label='Zoom in']")?.disabled).toBe(false);
  });

  it("shows the format note and does not throw when the waveform is unavailable", async () => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/waveform/overview")) {
        return Promise.resolve(json({ available: false, columns: 0, bands: 16, data: [] }));
      }
      if (url.includes("/api/waveform")) {
        return Promise.resolve(json({ available: false, error: "waveform unavailable" }));
      }
      return Promise.reject(new Error(url));
    });
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, hooks());
    view.setTrack(3);
    await vi.waitUntil(() => host.dataset.waveformState === "unavailable");
    const note = host.querySelector<HTMLElement>(".waveform-note");
    expect(note?.textContent).toBe(playerStrings.waveformUnavailable);
    expect(note?.hidden).toBe(false);
    expect(host.querySelector(".waveform-detail-wrap")?.hasAttribute("hidden")).toBe(true);
    expect(host.querySelector<HTMLButtonElement>("[aria-label='Zoom in']")?.disabled).toBe(true);
  });

  it("updates the overview slider about once a second, and immediately on seek", () => {
    let time = 0;
    let sync = (): void => {};
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountWaveform(host, {
      ...hooks((seconds) => {
        time = seconds;
        sync();
      }),
      getTime: () => time,
    });
    sync = () => view.sync();
    view.showComputed(parsedWave());
    const slider = host.querySelector(".waveform-overview");
    expect(slider?.getAttribute("aria-valuenow")).toBe("0");
    expect(slider?.getAttribute("aria-valuetext")).toBe("0");
    time = 0.4;
    view.sync();
    expect(slider?.getAttribute("aria-valuenow")).toBe("0");
    time = 1.2;
    view.sync();
    expect(slider?.getAttribute("aria-valuenow")).toBe("1.2");
    expect(slider?.getAttribute("aria-valuetext")).toBe("1.2");
    slider!.getBoundingClientRect = () =>
      ({
        left: 0,
        width: 200,
        top: 0,
        height: 36,
        right: 200,
        bottom: 36,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    slider!.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: 50, bubbles: true }));
    expect(slider?.getAttribute("aria-valuenow")).toBe("5");
    expect(slider?.getAttribute("aria-valuetext")).toBe("5");
  });
});

function parsedBody(): Uint8Array {
  const detail = [10, 4, 0, 0, 0, 0];
  const overview = [10, 4, 0, 0, 0, 0];
  const body = new Uint8Array(64 + detail.length + overview.length);
  body.set([0x53, 0x57, 0x46, 0x31], 0);
  const view = new DataView(body.buffer);
  view.setUint16(4, 64, true);
  view.setUint16(6, 1, true);
  view.setUint16(8, 3, true);
  view.setUint16(10, 1, true);
  view.setUint32(12, 44100, true);
  view.setUint32(16, 150000, true);
  view.setUint32(20, 1000, true);
  view.setUint32(24, 1, true);
  view.setUint32(28, 1, true);
  view.setUint32(32, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(40, 250000, true);
  view.setUint32(44, 4_000_000, true);
  body.set(detail, 64);
  body.set(overview, 70);
  return body;
}
