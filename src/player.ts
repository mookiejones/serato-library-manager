/**
 * Playback for one library track.
 *
 * One `<audio>` element plays `GET /api/audio`. The bar shows the title,
 * the artist, play/pause, a seek bar, elapsed and total time, and volume.
 * Strings live in `player-strings.ts`.
 *
 * Hotkeys for issue #134 import this module and call:
 *
 * - `play(trackId: number): void`
 * - `pause(): void`
 * - `togglePlayPause(): void`
 * - `seek(seconds: number): void`
 * - `seekBy(deltaSeconds: number): void`
 * - `isPlaying(): boolean`
 * - `getPlayerState(): PlayerSnapshot`
 * - `subscribe(listener: (state: PlayerSnapshot) => void): () => void`
 *
 * `bindSpaceToggle()` is the only key binding here. It listens for Space,
 * ignores typing targets, and calls `togglePlayPause`. Issue #134 replaces
 * that function. `togglePlayPause` does nothing when no track is loaded;
 * the Space binding plays the selected library track in that case.
 */

import { playerStrings } from "./player-strings";
import { state } from "./state";

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
let barUnsubscribe: (() => void) | null = null;

let titleNode: HTMLElement | null = null;
let artistNode: HTMLElement | null = null;
let statusNode: HTMLElement | null = null;
let toggleNode: HTMLButtonElement | null = null;
let seekNode: HTMLInputElement | null = null;
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
 * Return whether Space should be left for the focused control.
 *
 * An input, a textarea, a select, and a contenteditable element all take
 * the key. A contenteditable="false" ancestor does not.
 *
 * @param target Event target.
 * @returns True when the player must not handle Space.
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target.closest("input, textarea, select")) return true;
  let current: Element | null = target;
  while (current) {
    if (current instanceof HTMLElement) {
      const editable = contentEditableState(current);
      if (editable !== null) return editable;
    }
    current = current.parentElement;
  }
  return false;
}

/**
 * Return whether this element itself turns contenteditable on or off.
 *
 * ``null`` means inherit, so the caller keeps walking. The attribute and
 * the DOM property are both read: jsdom updates the property without
 * setting the attribute.
 *
 * @param element Candidate host.
 * @returns True, false, or null when the value is inherit.
 */
function contentEditableState(element: HTMLElement): boolean | null {
  const attr = element.getAttribute("contenteditable");
  if (attr !== null) {
    const value = attr.toLowerCase();
    if (value === "false") return false;
    if (value === "true" || value === "" || value === "plaintext-only") return true;
  }
  const raw = element.contentEditable;
  const prop = typeof raw === "string" ? raw.toLowerCase() : "";
  if (prop === "true" || prop === "plaintext-only") return true;
  if (prop === "false") return false;
  return null;
}

/**
 * Start a library track.
 *
 * The element loads `/api/audio?id=&space=`. The same track, already
 * loaded and paused, resumes. A different track starts at the beginning.
 * Nothing is written to the library.
 *
 * @param trackId Asset id from the track list.
 */
export function play(nextId: number): void {
  if (!Number.isInteger(nextId) || nextId < 0) return;
  const element = ensureMedia();
  if (trackId !== nextId || element.src === "") {
    const row = state.byId.get(nextId);
    title = row?.name || row?.title || playerStrings.untitled;
    artist = row?.artist ?? "";
    trackId = nextId;
    currentTime = 0;
    duration = 0;
    element.src = trackUrl(nextId);
    element.currentTime = 0;
  }
  error = "";
  playing = true;
  emit();
  const pending = element.play();
  if (pending && typeof pending.then === "function") {
    pending.catch(() => {
      if (trackId !== nextId) return;
      playing = false;
      error = playerStrings.cannotPlay;
      emit();
    });
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
 * Does nothing when no track has been loaded. Space uses this after it
 * has decided a track is already loaded.
 */
export function togglePlayPause(): void {
  if (trackId === null) return;
  if (playing) pause();
  else play(trackId);
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
 * Return whether the current track is playing.
 *
 * False when nothing is loaded and after pause or the end of the file.
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
 * Listen for Space and toggle play/pause.
 *
 * This is the only playback hotkey. Issue #134 replaces this function.
 * Space is ignored while focus is in an input, a textarea, a select, or
 * a contenteditable element, while it is held down, and while Ctrl, Alt,
 * or Meta is pressed. A button, link, or open dialog keeps the key so
 * that control can activate. When no track is loaded, Space plays the
 * selected library track instead of toggling silence.
 *
 * @returns Removes the listener.
 */
export function bindSpaceToggle(): () => void {
  const onKey = (event: KeyboardEvent) => {
    if (event.key !== " " || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
    if (event.defaultPrevented || isTypingTarget(event.target) || isActivationTarget(event.target)) return;
    if (isOpenDialog(event.target)) return;
    event.preventDefault();
    if (trackId === null) {
      const selected = selectedPlayableId();
      if (selected !== null) play(selected);
      return;
    }
    togglePlayPause();
  };
  document.addEventListener("keydown", onKey);
  return () => document.removeEventListener("keydown", onKey);
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
  trackId = null;
  title = "";
  artist = "";
  playing = false;
  currentTime = 0;
  duration = 0;
  error = "";
  seeking = false;
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
    playing = false;
    emit();
  });
  element.addEventListener("ended", () => {
    playing = false;
    currentTime = element.currentTime;
    emit();
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
    playing = false;
    error = playerStrings.cannotPlay;
    emit();
  });
}

function trackUrl(nextId: number): string {
  // Id only. The route refuses a filesystem path, a ".." segment, and a percent-encoded id.
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

function isActivationTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return target.closest("button, a, summary, [role='button']") !== null;
}

function isOpenDialog(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const dialog = target.closest("dialog");
  return dialog instanceof HTMLDialogElement && dialog.open;
}

function emit(): void {
  const snapshot = getPlayerState();
  for (const listener of [...listeners]) listener(snapshot);
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

  toggleNode = document.createElement("button");
  toggleNode.type = "button";
  toggleNode.className = "player-toggle";
  toggleNode.addEventListener("click", () => togglePlayPause());

  const seekWrap = document.createElement("div");
  seekWrap.className = "player-seek";
  const elapsedWrap = document.createElement("span");
  elapsedWrap.className = "player-time";
  const elapsedLabel = document.createElement("span");
  elapsedLabel.className = "visually-hidden";
  elapsedLabel.textContent = playerStrings.elapsed;
  elapsedNode = document.createElement("span");
  elapsedWrap.append(elapsedLabel, elapsedNode);
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
  const totalWrap = document.createElement("span");
  totalWrap.className = "player-time";
  const totalLabel = document.createElement("span");
  totalLabel.className = "visually-hidden";
  totalLabel.textContent = playerStrings.duration;
  totalNode = document.createElement("span");
  totalWrap.append(totalLabel, totalNode);
  seekWrap.append(elapsedWrap, seekNode, totalWrap);

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
  bar.append(meta, toggleNode, seekWrap, volumeLabel);
  return bar;
}

function paintBar(): void {
  if (!titleNode || !artistNode || !statusNode || !toggleNode || !seekNode || !elapsedNode || !totalNode) return;
  const loaded = trackId !== null;
  titleNode.textContent = loaded ? (title || playerStrings.untitled) : playerStrings.nothingPlaying;
  artistNode.textContent = artist;
  artistNode.hidden = artist === "";
  statusNode.textContent = error;
  statusNode.hidden = error === "";
  toggleNode.textContent = playing ? playerStrings.pause : playerStrings.play;
  toggleNode.disabled = !loaded;
  toggleNode.setAttribute("aria-pressed", String(playing));
  const limit = Number.isFinite(duration) && duration > 0 ? duration : 0;
  seekNode.max = String(limit);
  seekNode.disabled = !loaded || limit === 0;
  if (!seeking) seekNode.value = String(Math.min(currentTime, limit || currentTime));
  elapsedNode.textContent = formatPlayerTime(currentTime);
  totalNode.textContent = formatPlayerTime(duration);
}
