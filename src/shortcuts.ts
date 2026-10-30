/**
 * Keyboard shortcuts for the library screen.
 *
 * SHORTCUTS is the only list. The key handler and the cheat sheet both
 * read it. Space and the left and right arrows call the registered
 * player. The player exports togglePlayPause and seekBy. When no player
 * is registered, those keys do nothing.
 */

import { copy } from "./copy";
import { el } from "./dom";
import { state } from "./state";
import { moveTrackList, openTrackList } from "./virtual-scroll";
import { closeQuickOpen, openQuickOpen, quickOpenIsOpen, wireQuickOpen } from "./quick-open";
import { focusCrateItem, moveFileList, openFileList, selectCrate, setMode } from "./views";

/** Seconds the seek keys pass to PlayerControls.seekBy. */
export const SEEK_SECONDS = 5;

/**
 * Playback hooks from the audio player.
 *
 * Register the player's togglePlayPause and seekBy. This table owns
 * Space and the seek keys, so the player does not bind them itself.
 */
export interface PlayerControls {
  togglePlayPause(): void;
  seekBy(deltaSeconds: number): void;
}

export interface ShortcutChord {
  /** KeyboardEvent.key value. */
  key: string;
  /** Ctrl on Windows and Linux, Command on macOS. */
  mod?: boolean;
  shift?: boolean;
}

export interface Shortcut {
  id: string;
  /** Cheat-sheet action. This is the English source for that row. */
  label: string;
  /** Cheat-sheet section, in table order. */
  group: string;
  keys: readonly ShortcutChord[];
  /** True only for Esc, which still runs while a field is focused. */
  whileTyping: boolean;
}

const SHORTCUT_DEFS = [
  {
    id: "focus-search",
    label: "Focus search",
    group: "Find",
    keys: [{ key: "f", mod: true }, { key: "/" }],
    whileTyping: false,
  },
  {
    id: "quick-open",
    label: "Find a track or file",
    group: "Find",
    keys: [{ key: "k", mod: true }],
    whileTyping: false,
  },
  {
    id: "dismiss",
    label: "Close or clear search",
    group: "Find",
    keys: [{ key: "Escape" }],
    whileTyping: true,
  },
  {
    id: "cheat-sheet",
    label: "Show shortcuts",
    group: "Find",
    keys: [{ key: "?" }],
    whileTyping: false,
  },
  {
    id: "list-previous",
    label: "Previous row",
    group: "Lists",
    keys: [{ key: "ArrowUp" }],
    whileTyping: false,
  },
  {
    id: "list-next",
    label: "Next row",
    group: "Lists",
    keys: [{ key: "ArrowDown" }],
    whileTyping: false,
  },
  {
    id: "list-open",
    label: "Open the row",
    group: "Lists",
    keys: [{ key: "Enter" }],
    whileTyping: false,
  },
  {
    id: "play-pause",
    label: "Play or pause",
    group: "Play",
    keys: [{ key: " " }],
    whileTyping: false,
  },
  {
    id: "seek-back",
    label: "Back 5 seconds",
    group: "Play",
    keys: [{ key: "ArrowLeft" }],
    whileTyping: false,
  },
  {
    id: "seek-forward",
    label: "Forward 5 seconds",
    group: "Play",
    keys: [{ key: "ArrowRight" }],
    whileTyping: false,
  },
  {
    id: "view-library",
    label: "Library",
    group: "Views",
    keys: [{ key: "1", mod: true }],
    whileTyping: false,
  },
  {
    id: "view-crates",
    label: "Crates",
    group: "Views",
    keys: [{ key: "2", mod: true }],
    whileTyping: false,
  },
  {
    id: "view-files",
    label: "Files",
    group: "Views",
    keys: [{ key: "3", mod: true }],
    whileTyping: false,
  },
  {
    id: "view-history",
    label: "History",
    group: "Views",
    keys: [{ key: "4", mod: true }],
    whileTyping: false,
  },
  {
    id: "view-snapshots",
    label: "Snapshots",
    group: "Views",
    keys: [{ key: "5", mod: true }],
    whileTyping: false,
  },
] as const;

export const SHORTCUTS: readonly Shortcut[] = SHORTCUT_DEFS;

export type ShortcutId = (typeof SHORTCUT_DEFS)[number]["id"];

let player: PlayerControls | null = null;
let returnFocus: HTMLElement | null = null;
let snapshotCursor = 0;

/**
 * Register or clear the audio player.
 *
 * Pass null when the player is removed. Space and the seek keys then
 * do nothing.
 *
 * @param controls Player functions, or null.
 * @returns {void}
 */
export function registerPlayerControls(controls: PlayerControls | null): void {
  player = controls;
}

/**
 * Return the registered player, if any.
 *
 * @returns The player, or null when playback is not connected.
 */
export function registeredPlayer(): PlayerControls | null {
  return player;
}

/**
 * Return whether a key event matches one chord.
 *
 * Ctrl and Command both count as mod. Alt does not. "?" matches the
 * question-mark key whether or not Shift is reported with it.
 *
 * @param chord Chord from the shortcut table.
 * @param event Key event.
 * @returns True when the event is that chord.
 */
export function chordMatches(chord: ShortcutChord, event: KeyboardEvent): boolean {
  if (event.altKey) return false;
  const mod = event.ctrlKey || event.metaKey;
  if (mod !== Boolean(chord.mod)) return false;
  if (chord.key === "?") return event.key === "?" && !mod;
  if (event.shiftKey !== Boolean(chord.shift)) return false;
  if (chord.key === " ") return event.key === " ";
  return event.key === chord.key || event.key.toLowerCase() === chord.key.toLowerCase();
}

/**
 * Return the shortcut whose chord matches the event.
 *
 * @param event Key event.
 * @returns The shortcut, or null when nothing matches.
 */
export function matchShortcut(event: KeyboardEvent): Shortcut | null {
  for (const shortcut of SHORTCUTS) {
    if (shortcut.keys.some((chord) => chordMatches(chord, event))) return shortcut;
  }
  return null;
}

/**
 * Return the cheat-sheet text for one chord.
 *
 * The sheet prints this instead of a second copy of the binding.
 *
 * @param chord Chord from the shortcut table.
 * @returns The label, such as Ctrl/Cmd+K or Esc.
 */
export function chordLabel(chord: ShortcutChord): string {
  const names: Record<string, string> = {
    Escape: "Esc",
    " ": "Space",
    ArrowLeft: "Left arrow",
    ArrowRight: "Right arrow",
    ArrowUp: "Up arrow",
    ArrowDown: "Down arrow",
    Enter: "Enter",
  };
  const named = names[chord.key];
  if (named) return named;
  const key = chord.key.length === 1 ? chord.key.toUpperCase() : chord.key;
  return chord.mod ? `Ctrl/Cmd+${key}` : key;
}

/**
 * Return whether the event target is a field the person is typing in.
 *
 * Checkboxes, radios, and buttons are not fields. A content-editable
 * region is a field.
 *
 * @param target Event target.
 * @returns True when shortcuts other than Esc must stay quiet.
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const field = target.closest("input, textarea, select");
  if (!(field instanceof HTMLElement)) return false;
  if (field instanceof HTMLInputElement) {
    const inert = new Set(["button", "checkbox", "radio", "file", "range", "color", "submit", "reset"]);
    if (inert.has(field.type)) return false;
  }
  return true;
}

/**
 * Fill the cheat sheet from SHORTCUTS and show it.
 *
 * Focus moves to the heading. Esc closes the dialog and returns focus.
 *
 * @returns {void}
 */
export function openCheatSheet(): void {
  const dialog = el("shortcuts-dialog");
  if (dialog.open) return;
  rememberFocus();
  renderCheatSheet();
  dialog.showModal();
  el("shortcuts-title").tabIndex = -1;
  el("shortcuts-title").focus();
}

/**
 * Attach the shortcut keys and the cheat-sheet button.
 *
 * Called once at startup, and again in tests after the page markup is
 * replaced. Does not fetch.
 *
 * @returns {void}
 */
export function wireShortcuts(): void {
  document.removeEventListener("keydown", onKey);
  document.addEventListener("keydown", onKey);
  el("open-shortcuts").addEventListener("click", () => openCheatSheet());
  el("shortcuts-close").addEventListener("click", () => el("shortcuts-dialog").close());
  el("shortcuts-dialog").addEventListener("close", () => restoreFocus());
  wireQuickOpen();
}

function onKey(event: KeyboardEvent): void {
  if (event.isComposing || event.defaultPrevented) return;
  const shortcut = matchShortcut(event);
  if (!shortcut) return;
  if (isTypingTarget(event.target) && !shortcut.whileTyping) return;
  if (shortcut.id !== "dismiss" && topDialog()) return;
  if (skipsListKey(shortcut.id, event.target)) return;
  if (event.repeat && !repeats(shortcut.id)) return;
  runShortcut(shortcut.id, event);
}

function repeats(id: string): boolean {
  return id === "list-previous" || id === "list-next" || id === "seek-back" || id === "seek-forward";
}

function skipsListKey(id: string, target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (id === "play-pause" && target.closest("button, a, summary, input, select, textarea, [role='button']")) return true;
  if (id === "list-open" && target.closest("button, a, summary, textarea, select")) return true;
  return false;
}

function topDialog(): HTMLDialogElement | null {
  const open = [...document.querySelectorAll("dialog")].filter(
    (node): node is HTMLDialogElement => node instanceof HTMLDialogElement && node.open,
  );
  return open.at(-1) ?? null;
}

const HANDLERS: { [K in ShortcutId]: (event: KeyboardEvent) => void } = {
  "focus-search": (event) => {
    event.preventDefault();
    focusCurrentSearch();
  },
  "quick-open": (event) => {
    event.preventDefault();
    openQuickOpen();
  },
  dismiss: (event) => {
    dismiss(event);
  },
  "cheat-sheet": (event) => {
    event.preventDefault();
    openCheatSheet();
  },
  "list-previous": (event) => {
    event.preventDefault();
    moveActiveList(-1);
  },
  "list-next": (event) => {
    event.preventDefault();
    moveActiveList(1);
  },
  "list-open": (event) => {
    event.preventDefault();
    openActiveList();
  },
  "play-pause": (event) => {
    if (!player) return;
    event.preventDefault();
    player.togglePlayPause();
  },
  "seek-back": (event) => {
    if (!player) return;
    event.preventDefault();
    player.seekBy(-SEEK_SECONDS);
  },
  "seek-forward": (event) => {
    if (!player) return;
    event.preventDefault();
    player.seekBy(SEEK_SECONDS);
  },
  "view-library": (event) => {
    event.preventDefault();
    showLibrary();
  },
  "view-crates": (event) => {
    event.preventDefault();
    showCrates();
  },
  "view-files": (event) => {
    event.preventDefault();
    setMode("files");
    el("files-list").focus();
  },
  "view-history": (event) => {
    event.preventDefault();
    setMode("history");
    el("list").focus();
  },
  "view-snapshots": (event) => {
    event.preventDefault();
    setMode("snapshots");
    snapshotCursor = 0;
    el("snapshots-list").focus();
  },
};

function runShortcut(id: string, event: KeyboardEvent): void {
  const handler = HANDLERS[id as ShortcutId];
  handler(event);
}

function focusCurrentSearch(): void {
  if (state.mode === "files") {
    const field = el("files-search");
    field.focus();
    field.select();
    return;
  }
  if (state.mode === "snapshots") {
    el("snapshots-status").textContent = copy.snapshotsNoSearch;
    return;
  }
  const field = el("search");
  field.focus();
  field.select();
}

function showLibrary(): void {
  setMode("crates");
  selectCrate("all");
  el("list").focus();
}

function showCrates(): void {
  setMode("crates");
  const first = el("crate-list").querySelector<HTMLButtonElement>(".crate");
  if (first) focusCrateItem(first);
  else el("crate-list").focus();
}

function moveActiveList(delta: number): void {
  if (quickOpenIsOpen()) return;
  if (state.mode === "files") {
    moveFileList(delta);
    return;
  }
  if (state.mode === "snapshots") {
    moveSnapshots(delta);
    return;
  }
  moveTrackList(delta);
}

function openActiveList(): void {
  if (quickOpenIsOpen()) return;
  if (state.mode === "files") {
    openFileList();
    return;
  }
  if (state.mode === "snapshots") {
    openSnapshot();
    return;
  }
  openTrackList();
}

function moveSnapshots(delta: number): void {
  const cards = snapshotCards();
  if (!cards.length) return;
  snapshotCursor = Math.max(0, Math.min(cards.length - 1, snapshotCursor + delta));
  const card = cards[snapshotCursor];
  card?.querySelector("button")?.focus();
}

function openSnapshot(): void {
  const cards = snapshotCards();
  const card = cards[snapshotCursor] ?? cards[0];
  card?.querySelector("button")?.click();
}

function snapshotCards(): HTMLElement[] {
  return [...el("snapshots-list").querySelectorAll<HTMLElement>(".snapshot-card")];
}

function dismiss(event: KeyboardEvent): void {
  const dialog = topDialog();
  if (dialog) {
    if (dialog.id === "quick-open") {
      event.preventDefault();
      closeQuickOpen();
      return;
    }
    if (dialog.id === "shortcuts-dialog") {
      event.preventDefault();
      dialog.close();
      return;
    }
    return;
  }
  const active = document.activeElement;
  if (active instanceof HTMLInputElement && isSearchField(active)) {
    event.preventDefault();
    if (active.value) replaceInput(active, "");
    else active.blur();
    return;
  }
  if (isTypingTarget(active)) {
    if (active instanceof HTMLElement) active.blur();
    return;
  }
  if (clearViewSearch()) event.preventDefault();
}

function isSearchField(field: HTMLInputElement): boolean {
  return field.id === "search" || field.id === "crate-search" || field.id === "files-search" || field.id === "quick-open-query";
}

function clearViewSearch(): boolean {
  if (state.mode === "files" && el("files-search").value) {
    replaceInput(el("files-search"), "");
    return true;
  }
  if (state.mode === "crates" && el("crate-search").value && !el("search").value) {
    replaceInput(el("crate-search"), "");
    return true;
  }
  if (el("search").value) {
    replaceInput(el("search"), "");
    return true;
  }
  if (el("crate-search").value) {
    replaceInput(el("crate-search"), "");
    return true;
  }
  return false;
}

function replaceInput(field: HTMLInputElement, value: string): void {
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function renderCheatSheet(): void {
  el("shortcuts-title").textContent = copy.shortcutsTitle;
  el("shortcuts-intro").textContent = copy.shortcutsIntro;
  el("shortcuts-close").textContent = copy.shortcutsClose;
  const body = el("shortcuts-body");
  body.replaceChildren();
  const groups: string[] = [];
  for (const shortcut of SHORTCUTS) {
    if (!groups.includes(shortcut.group)) groups.push(shortcut.group);
  }
  for (const group of groups) {
    const heading = document.createElement("h3");
    heading.textContent = group;
    body.append(heading);
    if (group === "Play") {
      const note = document.createElement("p");
      note.className = "dialog-note";
      note.textContent = copy.playNote;
      body.append(note);
    }
    const table = document.createElement("table");
    table.className = "shortcut-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const actionHead = document.createElement("th");
    actionHead.scope = "col";
    actionHead.textContent = "Action";
    const keyHead = document.createElement("th");
    keyHead.scope = "col";
    keyHead.textContent = "Key";
    headRow.append(actionHead, keyHead);
    head.append(headRow);
    const rows = document.createElement("tbody");
    for (const shortcut of SHORTCUTS) {
      if (shortcut.group !== group) continue;
      const row = document.createElement("tr");
      const action = document.createElement("th");
      action.scope = "row";
      action.textContent = shortcut.label;
      const keys = document.createElement("td");
      shortcut.keys.forEach((chord, index) => {
        if (index > 0) keys.append(document.createTextNode(" or "));
        const kbd = document.createElement("kbd");
        kbd.textContent = chordLabel(chord);
        keys.append(kbd);
      });
      row.append(action, keys);
      rows.append(row);
    }
    table.append(head, rows);
    body.append(table);
  }
}

function rememberFocus(): void {
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
}

function restoreFocus(): void {
  const node = returnFocus;
  returnFocus = null;
  if (node && node.isConnected) node.focus();
}
