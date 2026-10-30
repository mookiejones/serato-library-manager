/**
 * Playback for one library track.
 *
 * One `<audio>` element plays `GET /api/audio`. The bar shows the title,
 * the artist, previous, play/pause, next, a seek bar with cue markers,
 * elapsed and total time, volume, and the waveform. Strings live in
 * `player-strings.ts`. Cue points, loops, and the beatgrid come from
 * `GET /api/track` and are not written back. The waveform is
 * `waveform-view.ts`. Space and the seek keys stay in the shortcut table.
 *
 * Hotkeys import this module and call:
 *
 * - `play(trackId: number): void`
 * - `pause(): void`
 * - `togglePlayPause(): void`
 * - `next(): void`
 * - `previous(): void`
 * - `seek(seconds: number): void`
 * - `seekBy(deltaSeconds: number): void`
 * - `isPlaying(): boolean`
 * - `getPlayerState(): PlayerSnapshot`
 * - `subscribe(listener: (state: PlayerSnapshot) => void): () => void`
 *
 * `playerControls` is what `app.ts` passes to `registerPlayerControls` right
 * after `mountPlayer()`. The shortcut table is the only Space listener.
 * `togglePlayPause` plays the selected library track when nothing is loaded.
 * The table's Left and Right call `seekBy` with 5 seconds. On the seek bar,
 * Left and Right move `SEEK_STEP_SECONDS` (5) and Shift moves
 * `SEEK_STEP_LARGE_SECONDS` (30). That handler marks the event handled so
 * the table does not seek a second time.
 */

import type { Marker, Track } from "./api-types";
import { playerStrings } from "./player-strings";
import { state } from "./state";
import { beatgridFromMarkers, loopsFromMarkers } from "./waveform";
import { mountWaveform, type WaveformController } from "./waveform-view";

export interface PlayerSnapshot {
  trackId: number | null;
  title: string;
  artist: string;
  playing: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  error: string;
}

export type PlayerListener = (state: PlayerSnapshot) => void;

/**
 * Hooks the shortcut table registers.
 *
 * Space and the global seek keys stay in that table. This module does not
 * add a document listener for them.
 */
export interface PlayerControls {
  togglePlayPause(): void;
  seekBy(deltaSeconds: number): void;
}

/** Seconds for one press of Left or Right on the seek bar. */
export const SEEK_STEP_SECONDS = 5;

/** Seconds for Shift with Left or Right on the seek bar. */
export const SEEK_STEP_LARGE_SECONDS = 30;

/**
 * One cue drawn on the seek bar.
 *
 * `seconds` is the position from the file. `color` is a `#` hex string, or
 * empty when the file did not give a usable color. `label` is the cue name.
 */
export interface CueMarker {
  seconds: number;
  color: string;
  label: string;
}

/**
 * The small surface the player needs from an audio element.
 *
 * A test can pass a fake. The page uses a real `<audio>` element.
 */
export interface PlayableMedia {
  src: string;
  currentTime: number;
  readonly duration: number;
  volume: number;
  readonly paused: boolean;
  play(): Promise<void> | void;
  pause(): void;
  addEventListener(type: string, listener: () => void): void;
  removeEventListener(type: string, listener: () => void): void;
}

const listeners = new Set<PlayerListener>();
const wired = new WeakSet<object>();
const CUE_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

let media: PlayableMedia | null = null;
let trackId: number | null = null;
let title = "";
let artist = "";
let playing = false;
let currentTime = 0;
let duration = 0;
let volume = 1;
let error = "";
let seeking = false;
let ignoreMediaPause = false;
let cueToken = 0;
let cues: CueMarker[] = [];
let paintedCueKey = "";
let barUnsubscribe: (() => void) | null = null;
let waveform: WaveformController | null = null;

let titleNode: HTMLElement | null = null;
let artistNode: HTMLElement | null = null;
let statusNode: HTMLElement | null = null;
let toggleNode: HTMLButtonElement | null = null;
let previousNode: HTMLButtonElement | null = null;
let nextNode: HTMLButtonElement | null = null;
let seekNode: HTMLInputElement | null = null;
let cueLayer: HTMLElement | null = null;
let elapsedNode: HTMLElement | null = null;
let totalNode: HTMLElement | null = null;

/**
 * Format a playback position as m:ss, or h:mm:ss past an hour.
 *
 * A value that is not a finite number is shown as 0:00. No request is made.
 *
 * @param seconds Position or duration in seconds.
 * @returns The clock label.
 */
export function formatPlayerTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  const secs = total % 60;
  const minutes = Math.floor(total / 60);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

/**
 * Turn Serato cue rows into seek-bar markers.
 *
 * A row without a finite start time is dropped. The name falls back to
 * `Cue` plus the stored index. A color that is not a `#` hex value is
 * left blank so the bar uses its default. Nothing is written.
 *
 * @param rows Cue rows from `GET /api/track`, or undefined when there are none.
 * @returns Markers in the order they were given. Empty when there are no cues.
 */
export function markersFromCues(rows: readonly Marker[] | undefined): CueMarker[] {
  if (!rows || rows.length === 0) return [];
  const found: CueMarker[] = [];
  for (const cue of rows) {
    const start = Number(cue.start_ms);
    if (!Number.isFinite(start) || start < 0) continue;
    const index = Number(cue.index);
    const named = typeof cue.name === "string" ? cue.name.trim() : "";
    const fallback = Number.isInteger(index) ? index + 1 : found.length + 1;
    const color = typeof cue.color === "string" && CUE_COLOR.test(cue.color) ? cue.color : "";
    found.push({
      seconds: start / 1000,
      color,
      label: named || `${playerStrings.cue} ${fallback}`,
    });
  }
  return found;
}

/**
 * Choose the status line for a failed audio response.
 *
 * 403 and 404 mean the id is not a library file that can be opened. Any
 * other status, including a decode failure with no status, keeps the
 * window message.
 *
 * @param status HTTP status from `HEAD /api/audio`. Zero when the probe failed.
 * @returns The sentence shown in the player bar.
 */
export function playbackErrorText(status: number): string {
  if (status === 403 || status === 404) return playerStrings.notInLibrary;
  return playerStrings.cannotPlay;
}

/**
 * Start a library track.
 *
 * The element loads `/api/audio?id=&space=`. The same track, already
 * loaded and paused, resumes. A different track starts at the beginning.
 * Cue markers are read from `GET /api/track`. Nothing is written to the library.
 *
 * @param trackId Asset id from the track list.
 */
export function play(nextId: number): void {
  if (!Number.isInteger(nextId) || nextId < 0) return;
  const element = ensureMedia();
  ignoreMediaPause = true;
  try {
    if (trackId !== nextId || element.src === "") {
      const row = state.byId.get(nextId);
      title = row?.name || row?.title || playerStrings.untitled;
      artist = row?.artist ?? "";
      trackId = nextId;
      currentTime = 0;
      duration = 0;
      element.src = trackUrl(nextId);
      element.currentTime = 0;
      waveform?.setTrack(nextId);
      loadCues(nextId);
    }
    error = "";
    playing = true;
    emit();
    const pending = element.play();
    if (pending && typeof pending.then === "function") {
      pending.catch(() => {
        if (trackId !== nextId) return;
        noteFailure(nextId);
      });
    }
  } finally {
    ignoreMediaPause = false;
  }
}

/**
 * Pause the current track.
 *
 * Does nothing when no track has been loaded. The library is not written.
 */
export function pause(): void {
  if (trackId === null) return;
  playing = false;
  ensureMedia().pause();
  emit();
}

/**
 * Pause when audio is playing, and play when it is paused.
 *
 * When nothing is loaded, this plays the selected library track. A history
 * row and an empty selection do nothing. The shortcut table calls this for Space.
 */
export function togglePlayPause(): void {
  if (trackId === null) {
    const selected = selectedPlayableId();
    if (selected !== null) play(selected);
    return;
  }
  if (playing) pause();
  else play(trackId);
}

/**
 * Play the next row in the current visible list.
 *
 * Order is `state.view`, which is the filtered and sorted list. History
 * rows are skipped. When nothing is loaded, the selection is the starting
 * row, and a press with no selection starts at the first playable row.
 * The last row does not wrap.
 */
export function next(): void {
  moveBy(1);
}

/**
 * Play the previous row in the current visible list.
 *
 * The same order as `next`. The first row does not wrap. When nothing is
 * loaded and nothing is selected, this starts at the last playable row.
 */
export function previous(): void {
  moveBy(-1);
}

/**
 * Move the playhead to a position in seconds.
 *
 * Values before zero are clamped to the start. Values past a known
 * duration are clamped to the end. A non-finite number is ignored.
 * Does nothing when no track has been loaded.
 *
 * @param seconds Position in seconds.
 */
export function seek(seconds: number): void {
  if (!Number.isFinite(seconds) || trackId === null) return;
  const element = ensureMedia();
  let next = seconds < 0 ? 0 : seconds;
  const limit = element.duration;
  if (Number.isFinite(limit) && limit > 0 && next > limit) next = limit;
  element.currentTime = next;
  currentTime = next;
  emit();
}

/**
 * Move the playhead by a number of seconds.
 *
 * A positive delta moves forward. A negative delta moves back. Clamping
 * is the same as `seek`. A non-finite delta is ignored.
 *
 * @param deltaSeconds Seconds to add to the current position.
 */
export function seekBy(deltaSeconds: number): void {
  if (!Number.isFinite(deltaSeconds)) return;
  seek(currentTime + deltaSeconds);
}

/**
 * The player hooks the shortcut table registers once.
 *
 * Pass this object to `registerPlayerControls`. Do not also listen for Space.
 */
export const playerControls: PlayerControls = {
  togglePlayPause,
  seekBy,
};

/**
 * Return whether the current track is playing.
 *
 * False when nothing is loaded and after pause or the end of the file
 * when no later row starts.
 *
 * @returns True while playback is running.
 */
export function isPlaying(): boolean {
  return playing;
}

/**
 * Return a copy of the player state.
 *
 * The caller cannot change playback by editing the object. `subscribe`
 * receives the same shape after each change.
 *
 * @returns The current snapshot.
 */
export function getPlayerState(): PlayerSnapshot {
  return { trackId, title, artist, playing, currentTime, duration, volume, error };
}

/**
 * Run a callback after each playback change.
 *
 * The callback is not run immediately. Call `getPlayerState` for the
 * current snapshot. The returned function removes the callback.
 *
 * @param listener Called with a snapshot. Do not mutate it.
 * @returns Unsubscribes the listener.
 */
export function subscribe(listener: PlayerListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Give a test a media element that does not fetch.
 *
 * The page does not call this. `mountPlayer` uses a real `<audio>` element
 * when nothing has been attached.
 *
 * @param next Media stand-in. Events update the snapshot.
 */
export function attachMedia(next: PlayableMedia): void {
  media = next;
  next.volume = volume;
  wire(next);
}

/**
 * Paint the player bar into `#player-bar`.
 *
 * Called once from app.ts. A missing host does nothing, so a test page
 * that has not installed the markup can still call `play`.
 *
 * @param host Element to fill. Defaults to `#player-bar`.
 */
export function mountPlayer(host?: HTMLElement | null): void {
  barUnsubscribe?.();
  barUnsubscribe = null;
  waveform?.destroy();
  waveform = null;
  resetPlayback();
  const root = host === undefined ? document.getElementById("player-bar") : host;
  if (!root) return;
  root.classList.add("player-bar");
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", playerStrings.region);
  const element = ensureMedia();
  root.replaceChildren();
  if (element instanceof Node) root.append(element);
  root.append(buildBar());
  barUnsubscribe = subscribe(() => paintBar());
  paintBar();
}

function resetPlayback(): void {
  cueToken += 1;
  trackId = null;
  title = "";
  artist = "";
  playing = false;
  currentTime = 0;
  duration = 0;
  error = "";
  seeking = false;
  cues = [];
  paintedCueKey = "";
}

function ensureMedia(): PlayableMedia {
  if (media) return media;
  const audio = document.createElement("audio");
  audio.id = "player-audio";
  audio.preload = "none";
  audio.className = "player-audio";
  audio.volume = volume;
  media = audio;
  wire(audio);
  return audio;
}

function wire(element: PlayableMedia): void {
  if (wired.has(element)) return;
  wired.add(element);
  element.addEventListener("play", () => {
    playing = true;
    emit();
  });
  element.addEventListener("pause", () => {
    if (ignoreMediaPause) return;
    playing = false;
    emit();
  });
  element.addEventListener("ended", () => {
    currentTime = Number.isFinite(element.currentTime) ? element.currentTime : currentTime;
    if (!moveBy(1)) {
      playing = false;
      emit();
    }
  });
  element.addEventListener("timeupdate", () => {
    currentTime = element.currentTime;
    if (Number.isFinite(element.duration)) duration = element.duration;
    emit();
  });
  element.addEventListener("durationchange", () => {
    duration = Number.isFinite(element.duration) ? element.duration : 0;
    emit();
  });
  element.addEventListener("error", () => {
    if (trackId === null) return;
    noteFailure(trackId);
  });
}

function trackUrl(nextId: number): string {
  // Id only. A path parameter is refused by the route.
  const params = new URLSearchParams({ id: String(nextId), space: state.space });
  return `/api/audio?${params.toString()}`;
}

function selectedPlayableId(): number | null {
  if (state.mode === "history") return null;
  const selected = state.selectedId;
  if (selected === null) return null;
  const row = state.byId.get(selected);
  if (!row || row.entry) return null;
  return row.id;
}

function playableRows(): Track[] {
  return state.view.filter((row) => !row.entry && Number.isInteger(row.id) && row.id >= 0);
}

function anchorIndex(rows: readonly Track[]): number {
  if (trackId !== null) {
    const playingIndex = rows.findIndex((row) => row.id === trackId);
    if (playingIndex >= 0) return playingIndex;
  }
  if (state.selectedId === null) return -1;
  return rows.findIndex((row) => row.id === state.selectedId);
}

function moveBy(delta: 1 | -1): boolean {
  const rows = playableRows();
  if (rows.length === 0) return false;
  const index = anchorIndex(rows);
  const target = index < 0 ? rows[delta > 0 ? 0 : rows.length - 1] : rows[index + delta];
  if (!target) return false;
  play(target.id);
  return true;
}

function loadCues(id: number): void {
  const token = ++cueToken;
  cues = [];
  waveform?.setMarkers(id, { cues: [], loops: [], beatgrid: [] });
  void readCues(id).then(
    (found) => {
      if (token !== cueToken || trackId !== id) return;
      cues = found.cues;
      waveform?.setMarkers(id, found);
      emit();
    },
    () => {
      if (token !== cueToken || trackId !== id) return;
      cues = [];
      waveform?.setMarkers(id, { cues: [], loops: [], beatgrid: [] });
      emit();
    },
  );
}

async function readCues(id: number): Promise<{ cues: CueMarker[]; loops: ReturnType<typeof loopsFromMarkers>; beatgrid: ReturnType<typeof beatgridFromMarkers> }> {
  const empty = { cues: [], loops: [], beatgrid: [] };
  if (typeof fetch !== "function") return empty;
  const params = new URLSearchParams({ id: String(id), space: state.space });
  const response = await fetch(`/api/track?${params.toString()}`);
  if (!response.ok) return empty;
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object") return empty;
  const record = payload as { cues?: Marker[]; loops?: Marker[]; beatgrid?: Marker[] };
  return {
    cues: markersFromCues(record.cues),
    loops: loopsFromMarkers(record.loops),
    beatgrid: beatgridFromMarkers(record.beatgrid),
  };
}

function noteFailure(forId: number): void {
  playing = false;
  void classifyStatus(forId).then((message) => {
    if (trackId !== forId) return;
    playing = false;
    error = message;
    emit();
  });
}

async function classifyStatus(forId: number): Promise<string> {
  try {
    if (typeof fetch !== "function") return playerStrings.cannotPlay;
    const response = await fetch(trackUrl(forId), { method: "HEAD" });
    return playbackErrorText(response.status);
  } catch {
    return playerStrings.cannotPlay;
  }
}

function emit(): void {
  const snapshot = getPlayerState();
  for (const listener of [...listeners]) listener(snapshot);
  waveform?.sync();
}

function buildBar(): HTMLElement {
  const meta = document.createElement("div");
  meta.className = "player-meta";
  titleNode = document.createElement("p");
  titleNode.className = "player-title";
  artistNode = document.createElement("p");
  artistNode.className = "player-artist";
  statusNode = document.createElement("p");
  statusNode.className = "player-status";
  statusNode.setAttribute("role", "status");
  meta.append(titleNode, artistNode, statusNode);

  previousNode = document.createElement("button");
  previousNode.type = "button";
  previousNode.className = "player-toggle";
  previousNode.textContent = playerStrings.previous;
  previousNode.addEventListener("click", () => previous());

  toggleNode = document.createElement("button");
  toggleNode.type = "button";
  toggleNode.className = "player-toggle player-play";
  toggleNode.addEventListener("click", () => togglePlayPause());

  nextNode = document.createElement("button");
  nextNode.type = "button";
  nextNode.className = "player-toggle";
  nextNode.textContent = playerStrings.next;
  nextNode.addEventListener("click", () => next());

  const transport = document.createElement("div");
  transport.className = "player-transport";
  transport.append(previousNode, toggleNode, nextNode);

  const seekWrap = document.createElement("div");
  seekWrap.className = "player-seek";
  const elapsedWrap = document.createElement("span");
  elapsedWrap.className = "player-time";
  const elapsedLabel = document.createElement("span");
  elapsedLabel.className = "visually-hidden";
  elapsedLabel.textContent = playerStrings.elapsed;
  elapsedNode = document.createElement("span");
  elapsedWrap.append(elapsedLabel, elapsedNode);

  const track = document.createElement("div");
  track.className = "player-seek-track";
  seekNode = document.createElement("input");
  seekNode.type = "range";
  seekNode.className = "player-range";
  seekNode.min = "0";
  seekNode.max = "0";
  seekNode.step = "0.1";
  seekNode.value = "0";
  seekNode.setAttribute("aria-label", playerStrings.seek);
  seekNode.addEventListener("pointerdown", () => {
    seeking = true;
  });
  const release = () => {
    seeking = false;
  };
  seekNode.addEventListener("pointerup", release);
  seekNode.addEventListener("pointercancel", release);
  seekNode.addEventListener("input", () => {
    if (!seekNode) return;
    seek(Number(seekNode.value));
  });
  seekNode.addEventListener("keydown", onSeekKey);
  cueLayer = document.createElement("div");
  cueLayer.className = "player-cues";
  track.append(seekNode, cueLayer);

  const totalWrap = document.createElement("span");
  totalWrap.className = "player-time";
  const totalLabel = document.createElement("span");
  totalLabel.className = "visually-hidden";
  totalLabel.textContent = playerStrings.duration;
  totalNode = document.createElement("span");
  totalWrap.append(totalLabel, totalNode);
  seekWrap.append(elapsedWrap, track, totalWrap);

  const volumeLabel = document.createElement("label");
  volumeLabel.className = "player-volume";
  const volumeText = document.createElement("span");
  volumeText.textContent = playerStrings.volume;
  const volumeInput = document.createElement("input");
  volumeInput.type = "range";
  volumeInput.min = "0";
  volumeInput.max = "1";
  volumeInput.step = "0.01";
  volumeInput.value = String(volume);
  volumeInput.addEventListener("input", () => {
    const next = Number(volumeInput.value);
    if (!Number.isFinite(next)) return;
    volume = Math.min(1, Math.max(0, next));
    ensureMedia().volume = volume;
    emit();
  });
  volumeLabel.append(volumeText, volumeInput);

  const bar = document.createElement("div");
  bar.className = "player-controls";
  bar.append(meta, transport, seekWrap, volumeLabel);

  const waveHost = document.createElement("div");
  waveform = mountWaveform(waveHost, {
    seek,
    seekBy,
    getTime: () => {
      const value = ensureMedia().currentTime;
      return Number.isFinite(value) ? value : currentTime;
    },
    getDuration: () => {
      const value = ensureMedia().duration;
      if (Number.isFinite(value) && value > 0) return value;
      return duration;
    },
    getPlaying: () => playing,
    formatTime: formatPlayerTime,
    seekStep: SEEK_STEP_SECONDS,
    seekStepLarge: SEEK_STEP_LARGE_SECONDS,
  });
  const stack = document.createElement("div");
  stack.className = "player-stack";
  stack.append(waveHost, bar);
  return stack;
}

function onSeekKey(event: KeyboardEvent): void {
  if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
  const forward = event.key === "ArrowRight" || event.key === "ArrowUp";
  const back = event.key === "ArrowLeft" || event.key === "ArrowDown";
  if (!forward && !back) return;
  event.preventDefault();
  event.stopPropagation();
  const step = event.shiftKey ? SEEK_STEP_LARGE_SECONDS : SEEK_STEP_SECONDS;
  seekBy((forward ? 1 : -1) * step);
}

function paintBar(): void {
  if (!titleNode || !artistNode || !statusNode || !toggleNode || !previousNode || !nextNode) return;
  if (!seekNode || !elapsedNode || !totalNode) return;
  const loaded = trackId !== null;
  const shownTitle = loaded ? (title || playerStrings.untitled) : playerStrings.nothingPlaying;
  titleNode.textContent = shownTitle;
  titleNode.title = shownTitle;
  artistNode.textContent = artist;
  artistNode.hidden = artist === "";
  artistNode.title = artist;
  statusNode.textContent = error;
  statusNode.hidden = error === "";
  statusNode.title = error;
  const action = playing ? playerStrings.pause : playerStrings.play;
  const named = loaded ? (title || playerStrings.untitled) : "";
  toggleNode.textContent = action;
  toggleNode.disabled = !loaded && selectedPlayableId() === null;
  toggleNode.setAttribute("aria-pressed", String(playing));
  toggleNode.setAttribute("aria-label", named ? `${action} ${named}` : action);
  previousNode.disabled = !canMove(-1);
  nextNode.disabled = !canMove(1);
  previousNode.setAttribute("aria-label", playerStrings.previous);
  nextNode.setAttribute("aria-label", playerStrings.next);
  const limit = Number.isFinite(duration) && duration > 0 ? duration : 0;
  seekNode.max = String(limit);
  seekNode.disabled = !loaded || limit === 0;
  if (!seeking) seekNode.value = String(Math.min(currentTime, limit || currentTime));
  elapsedNode.textContent = formatPlayerTime(currentTime);
  totalNode.textContent = formatPlayerTime(duration);
  paintCues(limit);
}

function canMove(delta: 1 | -1): boolean {
  const rows = playableRows();
  if (rows.length === 0) return false;
  const index = anchorIndex(rows);
  if (index < 0) return true;
  return Boolean(rows[index + delta]);
}

function paintCues(limit: number): void {
  if (!cueLayer) return;
  const key = `${limit}|${cues.map((cue) => `${cue.seconds}:${cue.label}:${cue.color}`).join(";")}`;
  if (key === paintedCueKey) return;
  paintedCueKey = key;
  cueLayer.replaceChildren();
  if (!(limit > 0) || cues.length === 0) return;
  for (const cue of cues) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "player-cue";
    const ratio = Math.min(1, Math.max(0, cue.seconds / limit));
    const percent = Math.round(ratio * 1000) / 10;
    button.style.left = `${percent}%`;
    if (cue.color) button.style.setProperty("--cue", cue.color);
    const label = `${cue.label}, ${formatPlayerTime(cue.seconds)}`;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", () => {
      seek(cue.seconds);
    });
    cueLayer.append(button);
  }
}
