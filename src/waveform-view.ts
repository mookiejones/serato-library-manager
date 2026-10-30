/**
 * Canvas waveform for the player bar.
 *
 * The zoomed view keeps the playhead at the center and scrolls the track
 * past it from the audio element's current time, on requestAnimationFrame
 * while playback is running. The overview is the whole track. Serato
 * Overview columns are drawn as soon as they arrive. The computed overview
 * replaces them when `GET /api/waveform` finishes. Zoom is the plus and
 * minus buttons, and Ctrl or Command with the wheel. No shortcut is added.
 *
 * Strings come from `player-strings.ts`. Tooltips are title attributes.
 */

import { playerStrings } from "./player-strings";
import { state } from "./state";
import {
  DetailTiles,
  ZOOM_DEFAULT_PPS,
  ZOOM_MAX_PPS,
  ZOOM_MIN_PPS,
  drawOverviewMarks,
  overviewXToTime,
  parseSwf1,
  renderOverview,
  shadePlayed,
  timeToX,
  zoomPixelsPerSecond,
  type ParsedWaveform,
  type WaveMarkers,
} from "./waveform";

/** What the player supplies. This module does not import the player. */
export interface WaveformHooks {
  seek(seconds: number): void;
  seekBy(deltaSeconds: number): void;
  getTime(): number;
  getDuration(): number;
  getPlaying(): boolean;
  formatTime(seconds: number): string;
  seekStep: number;
  seekStepLarge: number;
}

export interface WaveformController {
  setTrack(id: number | null): void;
  setMarkers(id: number, markers: WaveMarkers): void;
  sync(): void;
  destroy(): void;
  showComputed(parsed: ParsedWaveform): void;
  pixelsPerSecond(): number;
}

const emptyMarkers = (): WaveMarkers => ({ cues: [], loops: [], beatgrid: [] });

/**
 * Build the waveform controls and return the hooks the player calls.
 *
 * The host is hidden until a track is loaded. A missing host does nothing
 * useful; the caller still gets a controller whose methods are safe.
 *
 * @param host Element that will hold the canvases and zoom buttons.
 * @param hooks Seek, time, and the existing seek steps. No new keys.
 * @returns The controller.
 */
export function mountWaveform(host: HTMLElement, hooks: WaveformHooks): WaveformController {
  return new WaveformView(host, hooks);
}

/**
 * Paint a fixed waveform for the screenshot harness.
 *
 * The playhead is at 8 seconds of a 20 second track. A red cue, a blue
 * loop, and a beatgrid with a downbeat away from the playhead are drawn
 * by the same renderer the player uses. Coordinates are written on the
 * canvases so a test can sample those pixels.
 *
 * @param host Element to fill.
 */
export function mountWaveformFixture(host: HTMLElement): void {
  const playhead = 8;
  const duration = 20;
  const view = mountWaveform(host, {
    seek() {},
    seekBy() {},
    getTime: () => playhead,
    getDuration: () => duration,
    getPlaying: () => false,
    formatTime: (seconds) => String(seconds),
    seekStep: 5,
    seekStepLarge: 30,
  });
  view.showComputed(fixtureWaveform(duration));
  view.setMarkers(1, fixtureMarkers());
  const paint = (): void => {
    view.sync();
    stampFixture(host, playhead, duration, view.pixelsPerSecond());
    if ((host.querySelector(".waveform-detail")?.clientWidth ?? 0) > 0) host.dataset.waveformFixture = "ready";
  };
  paint();
  requestAnimationFrame(() => {
    paint();
    requestAnimationFrame(paint);
  });
}

class WaveformView implements WaveformController {
  private readonly host: HTMLElement;
  private readonly hooks: WaveformHooks;
  private readonly detail: HTMLCanvasElement;
  private readonly overviewCanvas: HTMLCanvasElement;
  private readonly overviewHit: HTMLElement;
  private readonly reading: HTMLElement;
  private readonly note: HTMLElement;
  private readonly detailWrap: HTMLElement;
  private readonly zoomIn: HTMLButtonElement;
  private readonly zoomOut: HTMLButtonElement;
  private trackId: number | null = null;
  private token = 0;
  private pps = ZOOM_DEFAULT_PPS;
  private markers: WaveMarkers = emptyMarkers();
  private tiles: DetailTiles | null = null;
  private parsed: ParsedWaveform | null = null;
  private overviewSource: "serato" | "computed" | "" = "";
  private seratoColumns: number[][] = [];
  private overviewCache: Uint8ClampedArray | null = null;
  private overviewKey = "";
  private raf = 0;
  private dragging = false;
  private disposed = false;
  private readonly onWheel: (event: WheelEvent) => void;
  private readonly onResize: () => void;
  private resizeObserver: ResizeObserver | null = null;

  constructor(host: HTMLElement, hooks: WaveformHooks) {
    this.host = host;
    this.hooks = hooks;
    host.classList.add("player-wave");
    host.hidden = true;
    const main = document.createElement("div");
    main.className = "player-wave-main";
    this.detailWrap = document.createElement("div");
    this.detailWrap.className = "waveform-detail-wrap";
    this.detail = document.createElement("canvas");
    this.detail.className = "waveform-detail";
    this.detail.setAttribute("aria-hidden", "true");
    this.reading = document.createElement("p");
    this.reading.className = "waveform-reading";
    this.reading.textContent = playerStrings.waveformReading;
    this.detailWrap.append(this.detail, this.reading);
    this.note = document.createElement("p");
    this.note.className = "waveform-note";
    this.note.hidden = true;
    this.note.textContent = playerStrings.waveformUnavailable;
    this.overviewHit = document.createElement("div");
    this.overviewHit.className = "waveform-overview";
    this.overviewHit.tabIndex = 0;
    this.overviewHit.setAttribute("role", "slider");
    this.overviewHit.setAttribute("aria-label", playerStrings.overview);
    this.overviewHit.setAttribute("aria-orientation", "horizontal");
    this.overviewHit.title = playerStrings.overviewSeek;
    this.overviewCanvas = document.createElement("canvas");
    this.overviewCanvas.setAttribute("aria-hidden", "true");
    this.overviewHit.append(this.overviewCanvas);
    main.append(this.detailWrap, this.note, this.overviewHit);
    const zoom = document.createElement("div");
    zoom.className = "waveform-zoom";
    this.zoomIn = button(playerStrings.zoomIn, "+");
    this.zoomOut = button(playerStrings.zoomOut, "\u2212");
    this.zoomIn.addEventListener("click", () => this.setZoom(zoomPixelsPerSecond(this.pps, 1)));
    this.zoomOut.addEventListener("click", () => this.setZoom(zoomPixelsPerSecond(this.pps, -1)));
    zoom.append(this.zoomIn, this.zoomOut);
    host.append(main, zoom);
    this.onWheel = (event) => this.wheel(event);
    host.addEventListener("wheel", this.onWheel, { passive: false });
    this.overviewHit.addEventListener("pointerdown", (event) => this.pointerDown(event));
    this.overviewHit.addEventListener("pointermove", (event) => this.pointerMove(event));
    this.overviewHit.addEventListener("pointerup", (event) => this.pointerUp(event));
    this.overviewHit.addEventListener("pointercancel", (event) => this.pointerUp(event));
    this.overviewHit.addEventListener("keydown", (event) => this.overviewKeyDown(event));
    this.onResize = () => this.paint();
    if (typeof ResizeObserver === "function") {
      this.resizeObserver = new ResizeObserver(this.onResize);
      this.resizeObserver.observe(host);
    }
    this.syncZoomButtons();
  }

  /**
   * Load one track, or hide the waveform when playback is cleared.
   *
   * The same id does not fetch again. Overview and the SWF1 body are
   * requested together. Playback is not paused from here.
   *
   * @param id Library track id, or null when nothing is loaded.
   */
  setTrack(id: number | null): void {
    if (this.disposed) return;
    if (id !== null && id === this.trackId) return;
    this.token += 1;
    this.trackId = id;
    this.parsed = null;
    this.tiles = null;
    this.markers = emptyMarkers();
    this.overviewCache = null;
    this.overviewKey = "";
    this.overviewSource = "";
    this.seratoColumns = [];
    delete this.overviewHit.dataset.waveformOverview;
    if (id === null || !Number.isInteger(id) || id < 0) {
      this.host.hidden = true;
      this.stopLoop();
      return;
    }
    this.host.hidden = false;
    this.setPhase("reading");
    const mine = this.token;
    void this.load(id, mine);
  }

  /**
   * Store cues, loops, and the beatgrid for the loaded track.
   *
   * A response for a track that is no longer loaded is ignored.
   *
   * @param id Track the rows belong to.
   * @param markers Marks to draw. Colors stay as stored.
   */
  setMarkers(id: number, markers: WaveMarkers): void {
    if (id !== this.trackId) return;
    this.markers = markers;
    this.paint();
  }

  /**
   * Show a parsed waveform without fetching.
   *
   * The screenshot harness and tests use this. The host is shown.
   *
   * @param parsed SWF1 sections.
   */
  showComputed(parsed: ParsedWaveform): void {
    this.trackId = this.trackId ?? 1;
    this.host.hidden = false;
    this.applyComputed(parsed);
  }

  /**
   * Follow play, pause, and seek.
   *
   * While audio is playing, frames are scheduled from the audio clock.
   * A paused seek paints once.
   */
  sync(): void {
    if (this.disposed || this.host.hidden) return;
    if (this.hooks.getPlaying()) this.startLoop();
    else this.stopLoop();
    this.paint();
  }

  /**
   * Current zoom in CSS pixels per second.
   *
   * @returns The zoom the buttons and the wheel last set.
   */
  pixelsPerSecond(): number {
    return this.pps;
  }

  /**
   * Remove listeners and stop the animation frame.
   */
  destroy(): void {
    this.disposed = true;
    this.token += 1;
    this.stopLoop();
    this.host.removeEventListener("wheel", this.onWheel);
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
  }

  private async load(id: number, mine: number): Promise<void> {
    const overview = this.fetchOverview(id);
    const body = this.fetchWaveform(id);
    void overview.then((serato) => {
      if (mine !== this.token || !serato || serato.length === 0) return;
      if (this.overviewSource === "computed") return;
      this.seratoColumns = serato;
      this.overviewSource = "serato";
      this.overviewHit.dataset.waveformOverview = "serato";
      this.overviewCache = null;
      this.overviewKey = "";
      this.overviewHit.hidden = false;
      this.paint();
    });
    const waveform = await body;
    if (mine !== this.token) return;
    if (waveform === "unavailable") {
      this.parsed = null;
      this.tiles = null;
      this.setPhase("unavailable");
      this.paint();
      return;
    }
    if (waveform) this.applyComputed(waveform);
  }

  private applyComputed(parsed: ParsedWaveform): void {
    this.parsed = parsed;
    const rate = parsed.pointsPerSecond > 0 ? parsed.pointsPerSecond : 150;
    this.tiles = new DetailTiles(parsed.detail, parsed.detailCount, rate);
    this.overviewSource = "computed";
    this.overviewHit.dataset.waveformOverview = "computed";
    this.overviewCache = null;
    this.overviewKey = "";
    this.setPhase("ready");
    this.paint();
  }

  private async fetchOverview(id: number): Promise<number[][] | null> {
    try {
      if (typeof fetch !== "function") return null;
      const response = await fetch(waveformUrl(id, true));
      if (!response.ok) return null;
      const payload: unknown = await response.json();
      if (!payload || typeof payload !== "object") return null;
      const record = payload as { available?: unknown; data?: unknown };
      if (record.available !== true || !Array.isArray(record.data)) return null;
      const columns: number[][] = [];
      for (const column of record.data) {
        if (!Array.isArray(column)) continue;
        columns.push(column.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : 0)));
      }
      return columns;
    } catch {
      return null;
    }
  }

  private async fetchWaveform(id: number): Promise<ParsedWaveform | "unavailable" | null> {
    try {
      if (typeof fetch !== "function") return null;
      const response = await fetch(waveformUrl(id, false));
      if (!response.ok) return null;
      const buffer = await response.arrayBuffer();
      const parsed = parseSwf1(buffer);
      if (parsed) return parsed;
      const text = new TextDecoder().decode(buffer);
      try {
        const payload: unknown = JSON.parse(text);
        if (payload && typeof payload === "object" && (payload as { available?: unknown }).available === false) {
          return "unavailable";
        }
      } catch {
        return null;
      }
      return null;
    } catch {
      return null;
    }
  }

  private setPhase(phase: "reading" | "ready" | "unavailable"): void {
    this.host.dataset.waveformState = phase;
    const unavailable = phase === "unavailable";
    this.note.hidden = !unavailable;
    this.reading.hidden = phase !== "reading";
    this.detailWrap.hidden = unavailable;
    this.overviewHit.hidden = this.overviewSource === "";
    this.syncZoomButtons();
  }

  private setZoom(next: number): void {
    if (next === this.pps) {
      this.syncZoomButtons();
      return;
    }
    this.pps = next;
    this.tiles?.clear();
    this.syncZoomButtons();
    this.paint();
  }

  private syncZoomButtons(): void {
    const unavailable = this.host.dataset.waveformState === "unavailable";
    this.zoomIn.disabled = unavailable || this.pps >= ZOOM_MAX_PPS - 1e-9;
    this.zoomOut.disabled = unavailable || this.pps <= ZOOM_MIN_PPS + 1e-9;
  }

  private wheel(event: WheelEvent): void {
    if (!event.ctrlKey && !event.metaKey) return;
    if (this.host.dataset.waveformState === "unavailable") return;
    event.preventDefault();
    if (event.deltaY < 0) this.setZoom(zoomPixelsPerSecond(this.pps, 1));
    else if (event.deltaY > 0) this.setZoom(zoomPixelsPerSecond(this.pps, -1));
  }

  private pointerDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    this.dragging = true;
    if (typeof this.overviewHit.setPointerCapture === "function") {
      this.overviewHit.setPointerCapture(event.pointerId);
    }
    this.seekOverview(event);
  }

  private pointerMove(event: PointerEvent): void {
    if (!this.dragging) return;
    this.seekOverview(event);
  }

  private pointerUp(event: PointerEvent): void {
    if (!this.dragging) return;
    this.dragging = false;
    if (typeof this.overviewHit.hasPointerCapture === "function" && this.overviewHit.hasPointerCapture(event.pointerId)) {
      this.overviewHit.releasePointerCapture(event.pointerId);
    }
  }

  private seekOverview(event: PointerEvent): void {
    const rect = this.overviewHit.getBoundingClientRect();
    const duration = this.duration();
    const x = event.clientX - rect.left;
    this.hooks.seek(overviewXToTime(x, rect.width, duration));
  }

  private overviewKeyDown(event: KeyboardEvent): void {
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    const forward = event.key === "ArrowRight" || event.key === "ArrowUp";
    const back = event.key === "ArrowLeft" || event.key === "ArrowDown";
    if (!forward && !back) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? this.hooks.seekStepLarge : this.hooks.seekStep;
    this.hooks.seekBy((forward ? 1 : -1) * step);
  }

  private startLoop(): void {
    if (this.raf !== 0) return;
    const loop = (): void => {
      this.paint();
      if (this.hooks.getPlaying() && !this.disposed) this.raf = requestAnimationFrame(loop);
      else this.raf = 0;
    };
    this.raf = requestAnimationFrame(loop);
  }

  private stopLoop(): void {
    if (this.raf === 0) return;
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private paint(): void {
    if (this.disposed || this.host.hidden) return;
    const time = this.hooks.getTime();
    const duration = this.duration();
    this.paintDetail(time);
    this.paintOverview(time, duration);
    this.updateSlider(time, duration);
  }

  private paintDetail(time: number): void {
    if (!this.tiles || !this.parsed) return;
    const size = sizeCanvas(this.detail, 96);
    if (!size) return;
    const frame = new Uint8ClampedArray(size.width * size.height * 4);
    this.tiles.paint(frame, size.width, size.height, size.dpr, time, this.pps, this.markers);
    const context = this.detail.getContext("2d");
    if (!context) return;
    const image = context.createImageData(size.width, size.height);
    image.data.set(frame);
    context.putImageData(image, 0, 0);
  }

  private paintOverview(time: number, duration: number): void {
    const size = sizeCanvas(this.overviewCanvas, 36);
    if (!size) return;
    const source = this.overviewPixels(size.width, size.height);
    if (!source) return;
    const frame = source.slice();
    const played = duration > 0 ? (Math.min(duration, Math.max(0, time)) / duration) * size.width : 0;
    shadePlayed(frame, size.width, size.height, played);
    drawOverviewMarks(frame, size.width, size.height, duration > 0 ? duration : this.headerDuration(), time, this.markers);
    const context = this.overviewCanvas.getContext("2d");
    if (!context) return;
    const image = context.createImageData(size.width, size.height);
    image.data.set(frame);
    context.putImageData(image, 0, 0);
  }

  private overviewPixels(width: number, height: number): Uint8ClampedArray | null {
    const key = `${this.overviewSource}|${width}|${height}|${this.token}`;
    if (this.overviewCache && this.overviewKey === key) return this.overviewCache;
    if (this.overviewSource === "computed" && this.parsed && this.parsed.overviewCount > 0) {
      this.overviewCache = renderOverview(
        { kind: "computed", points: this.parsed.overview, count: this.parsed.overviewCount },
        width,
        height,
      );
      this.overviewKey = key;
      this.overviewHit.dataset.waveformOverview = "computed";
      return this.overviewCache;
    }
    if (this.overviewSource === "serato" && this.seratoColumns.length > 0) {
      this.overviewCache = renderOverview({ kind: "serato", columns: this.seratoColumns }, width, height);
      this.overviewKey = key;
      this.overviewHit.dataset.waveformOverview = "serato";
      return this.overviewCache;
    }
    return null;
  }

  private updateSlider(time: number, duration: number): void {
    const max = duration > 0 ? duration : 0;
    const now = Math.min(max, Math.max(0, Number.isFinite(time) ? time : 0));
    this.overviewHit.setAttribute("aria-valuemin", "0");
    this.overviewHit.setAttribute("aria-valuemax", String(max));
    this.overviewHit.setAttribute("aria-valuenow", String(now));
    this.overviewHit.setAttribute("aria-valuetext", this.hooks.formatTime(now));
  }

  private duration(): number {
    const fromAudio = this.hooks.getDuration();
    if (Number.isFinite(fromAudio) && fromAudio > 0) return fromAudio;
    return this.headerDuration();
  }

  private headerDuration(): number {
    if (!this.parsed || !(this.parsed.durationMs > 0)) return 0;
    return this.parsed.durationMs / 1000;
  }
}

function button(label: string, text: string): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "waveform-zoom-button";
  element.textContent = text;
  element.title = label;
  element.setAttribute("aria-label", label);
  return element;
}

function waveformUrl(id: number, overview: boolean): string {
  const params = new URLSearchParams({ id: String(id), space: state.space });
  const path = overview ? "/api/waveform/overview" : "/api/waveform";
  return `${path}?${params.toString()}`;
}

function sizeCanvas(canvas: HTMLCanvasElement, cssHeight: number): { width: number; height: number; dpr: number } | null {
  const cssWidth = canvas.clientWidth;
  if (!(cssWidth > 0)) return null;
  const dpr = typeof window !== "undefined" && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1;
  const width = Math.max(1, Math.round(cssWidth * dpr));
  const height = Math.max(1, Math.round(cssHeight * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, dpr };
}

function fixtureWaveform(durationSeconds: number): ParsedWaveform {
  const rate = 150;
  const count = rate * durationSeconds;
  const detail = new Uint8Array(count * 6);
  for (let index = 0; index < count; index += 1) {
    const t = index / rate;
    const low = Math.round(140 + 100 * Math.sin(t * 3));
    const mid = Math.round(80 + 70 * Math.sin(t * 7 + 1));
    const high = Math.round(40 + 50 * Math.sin(t * 13));
    const offset = index * 6;
    detail[offset] = low;
    detail[offset + 1] = Math.round(low * 0.45);
    detail[offset + 2] = mid;
    detail[offset + 3] = Math.round(mid * 0.4);
    detail[offset + 4] = high;
    detail[offset + 5] = Math.round(high * 0.35);
  }
  const overviewCount = 200;
  const overview = new Uint8Array(overviewCount * 6);
  for (let index = 0; index < overviewCount; index += 1) {
    const t = index / overviewCount;
    const low = Math.round(70 + 110 * Math.abs(Math.sin(t * Math.PI * 6)));
    const mid = Math.round(30 + 80 * Math.abs(Math.sin(t * Math.PI * 14 + 0.4)));
    const high = Math.round(15 + 50 * Math.abs(Math.sin(t * Math.PI * 22)));
    const offset = index * 6;
    overview[offset] = low;
    overview[offset + 1] = Math.round(low * 0.55);
    overview[offset + 2] = mid;
    overview[offset + 3] = Math.round(mid * 0.45);
    overview[offset + 4] = high;
    overview[offset + 5] = Math.round(high * 0.4);
  }
  return {
    version: 1,
    flags: 3,
    analyzerVersion: 1,
    sampleRate: 44100,
    pointsPerSecond: rate,
    durationMs: durationSeconds * 1000,
    detail,
    overview,
    serato: new Uint8Array(),
    detailCount: count,
    overviewCount,
    seratoColumns: 0,
    seratoBands: 0,
    lowHz: 250,
    highHz: 4000,
  };
}

function fixtureMarkers(): WaveMarkers {
  return {
    cues: [{ seconds: 9.25, color: "#CC0000" }],
    loops: [{ startSeconds: 6.15, endSeconds: 7.4, color: "#27AAE1" }],
    beatgrid: [
      { positionSeconds: 0, beats: 40 },
      { positionSeconds: 20, bpm: 120 },
    ],
  };
}

function stampFixture(host: HTMLElement, playhead: number, duration: number, pps: number): void {
  const detail = host.querySelector<HTMLCanvasElement>(".waveform-detail");
  const overview = host.querySelector<HTMLCanvasElement>(".waveform-overview canvas");
  if (!detail || !overview) return;
  const detailScale = detail.clientWidth > 0 ? detail.width / detail.clientWidth : 1;
  const cssWidth = detail.clientWidth || detail.width;
  detail.dataset.cueX = String(Math.round(timeToX(9.25, playhead, pps, cssWidth) * detailScale));
  detail.dataset.downbeatX = String(Math.round(timeToX(6, playhead, pps, cssWidth) * detailScale));
  detail.dataset.beatX = String(Math.round(timeToX(5.5, playhead, pps, cssWidth) * detailScale));
  detail.dataset.loopEdgeX = String(Math.round(timeToX(6.15, playhead, pps, cssWidth) * detailScale));
  detail.dataset.playheadX = String(Math.floor(detail.width / 2));
  const played = Math.round((playhead / duration) * overview.width);
  overview.dataset.playedX = String(played);
  overview.dataset.cueX = String(Math.round((9.25 / duration) * overview.width));
  overview.dataset.loopEdgeX = String(Math.round((6.15 / duration) * overview.width));
}
