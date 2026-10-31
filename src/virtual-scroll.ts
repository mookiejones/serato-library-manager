/**
 * Virtual track list.
 *
 * Row height is ROW from state.ts, which matches --row in app.css. Only
 * the rows inside the scroll window are in the DOM. mountTrackList appends
 * the spacer once, before the first paint.
 */

import type { Track } from "./api-types";
import { bridge } from "./bridge";
import { el } from "./dom";
import { clockLabel, colorHex, lengthLabel } from "./format";
import { getPlayerState, play, subscribe } from "./player";
import { playerStrings } from "./player-strings";
import { ROW, state } from "./state";
import { formatNumber, t } from "./i18n";
import { buttonEl, setTooltip } from "./tooltip";
import { playRow, selectRow } from "./tooltip-strings";

const spacer = document.createElement("div");
const rows = document.createElement("div");
spacer.className = "spacer";
rows.className = "rows";
spacer.append(rows);

/**
 * Append the scroll spacer to the track list.
 *
 * Called once when the page starts, and again in a test after the
 * document body is replaced. Appending an existing node moves it.
 * Does not fetch.
 *
 * @returns {void}
 */
export function mountTrackList(): void {
  el("list").append(spacer);
}

/**
 * Paint only the track rows inside the scroll window.
 *
 * Row height is ROW. Six extra rows above and below the window keep a
 * fast scroll from flashing empty space. Replaces the row container.
 * Does not fetch track details.
 *
 * @returns {void}
 */
export function paintRows() {
  const view = state.view || [];
  const height = el("list").clientHeight || 600;
  // Paint six rows past the window so a fast scroll does not flash empty space.
  const start = Math.max(0, Math.floor(el("list").scrollTop / ROW) - 6);
  const end = Math.min(view.length, Math.ceil((el("list").scrollTop + height) / ROW) + 6);
  spacer.style.height = `${view.length * ROW}px`;
  rows.style.transform = `translateY(${start * ROW}px)`;
  rows.replaceChildren();
  if (!view.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = state.mode === "duplicates" && !state.duplicateIds ? t("list.readingDuplicates") : t("list.noMatches");
    rows.append(empty);
    return;
  }
  for (let index = start; index < end; index += 1) {
    const track = view[index]!;
    const button = document.createElement("div");
    button.className = "row";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(track.id === state.selectedId));
    button.dataset.id = String(track.id);
    setTooltip(button, selectRow(track.name || "Untitled"));

    const titleCell = document.createElement("span");
    titleCell.className = "cell";
    const line = document.createElement("span");
    line.className = "title-line";
    if (!track.entry) {
      const playingNow = getPlayerState();
      const playingThis = playingNow.trackId === track.id && playingNow.playing;
      const playButton = buttonEl(playRow(track.name || playerStrings.untitled));
      playButton.className = "row-play";
      const labelName = track.name || playerStrings.untitled;
      playButton.setAttribute("aria-label", `${playerStrings.play} ${labelName}`);
      playButton.setAttribute("aria-pressed", String(playingThis));
      const icon = document.createElement("span");
      icon.className = "row-play-icon";
      icon.setAttribute("aria-hidden", "true");
      playButton.append(icon);
      playButton.addEventListener("click", (event) => {
        event.stopPropagation();
        bridge.selectTrack(track.id);
        play(track.id);
        el("list").focus({ preventScroll: true });
      });
      playButton.addEventListener("dblclick", (event) => event.stopPropagation());
      line.append(playButton);
    }
    const hex = colorHex(track.color);
    if (hex) {
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = hex;
      line.append(swatch);
    }
    if (track.emoji) {
      const emoji = document.createElement("span");
      emoji.textContent = track.emoji;
      line.append(emoji);
    }
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = track.name || t("track.untitled");
    line.append(title);
    if (track.missing) {
      const missing = document.createElement("span");
      missing.className = "missing-word";
      missing.textContent = t("track.missingBadge");
      line.append(missing);
    }
    if (track.stems) {
      const stems = document.createElement("span");
      stems.className = "missing-word";
      stems.textContent = t("track.stemsBadge");
      line.append(stems);
    }
    titleCell.append(line);

    const artist = document.createElement("span");
    artist.className = "cell";
    artist.textContent = track.artist ?? "";

    const third = document.createElement("span");
    third.className = "cell num";
    const fourth = document.createElement("span");
    fourth.className = "cell num";
    const fifth = document.createElement("span");
    fifth.className = "cell num";
    if (track.entry) {
      third.textContent = track.deck || "";
      fourth.textContent = track.played || "";
      fifth.textContent = clockLabel(track.start);
    } else {
      third.textContent = track.bpm == null ? "" : formatNumber(Math.round(Number(track.bpm) * 100) / 100, { maximumFractionDigits: 2 });
      fourth.textContent = track.key ?? "";
      fifth.textContent = lengthLabel(track.length_ms);
    }

    button.append(titleCell, artist, third, fourth, fifth);
    button.addEventListener("click", () => {
      if (track.entry) bridge.selectEntry(track.id);
      else bridge.selectTrack(track.id);
      el("list").focus({ preventScroll: true });
    });
    button.addEventListener("dblclick", () => {
      if (!track.entry) play(track.id);
    });
    rows.append(button);
  }
}

/**
 * Move the list selection by one visible row and keep it on screen.
 *
 * History rows call selectEntry. Library rows call selectTrack. The scroll
 * window follows the row so the selection does not leave the viewport.
 *
 * @param {number} delta 1 for the next row, -1 for the previous row.
 * @returns {void}
 */
/**
 * Move the track selection from a shortcut.
 *
 * The list's own arrow keys call the same helper. Does not fetch by
 * itself; selecting a row does.
 *
 * @param delta 1 for the next row, -1 for the previous row.
 * @returns {void}
 */
export function moveTrackList(delta: number): void {
  moveSelection(delta);
}

/**
 * Open the selected track in the detail pane.
 *
 * When nothing is selected, the first visible row opens. History rows
 * use the entry already loaded with the session.
 *
 * @returns {void}
 */
export function openTrackList(): void {
  const view = state.view || [];
  const current = view.find((track) => track.id === state.selectedId) ?? view[0];
  if (!current) return;
  if (current.entry) bridge.selectEntry(current.id);
  else void bridge.selectTrack(current.id);
}

function moveSelection(delta: number) {
  const view = state.view || [];
  const index = view.findIndex((track) => track.id === state.selectedId);
  const next = view[Math.max(0, Math.min(view.length - 1, index + delta))];
  if (!next) return;
  if (next.entry) bridge.selectEntry(next.id);
  else bridge.selectTrack(next.id);
  const rowTop = view.indexOf(next) * ROW;
  if (rowTop < el("list").scrollTop) el("list").scrollTop = rowTop;
  if (rowTop + ROW > el("list").scrollTop + el("list").clientHeight) {
    el("list").scrollTop = rowTop + ROW - el("list").clientHeight;
  }
}

/**
 * Return the track row that holds the event target.
 *
 * Enter on a focused row plays that row. Enter while the list itself is
 * focused plays the selection instead. A history row is left for the caller
 * to skip. Does not fetch.
 *
 * @param target Event target.
 * @returns The visible row, or undefined when the target is not a row.
 */
function focusedTrack(target: EventTarget | null): Track | undefined {
  if (!(target instanceof Element)) return undefined;
  const row = target.closest(".row");
  if (!row) return undefined;
  const id = Number(row.getAttribute("data-id"));
  if (!Number.isInteger(id)) return undefined;
  return state.view.find((item) => item.id === id);
}

/**
 * Attach scroll and arrow-key listeners on the track list.
 *
 * Called once from app.ts after mountTrackList. Scrolling paints the
 * window. Arrow keys move the selection.
 *
 * @returns {void}
 */
export function wireVirtualScroll(): void {
  el("list").addEventListener("scroll", () => paintRows());
  el("list").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
    } else if (event.key === "Enter") {
      const chosen = focusedTrack(event.target) ?? state.view.find((item) => item.id === state.selectedId);
      if (!chosen || chosen.entry) return;
      event.preventDefault();
      void bridge.selectTrack(chosen.id);
      play(chosen.id);
    }
  });
  let paintedId: number | null = null;
  let paintedPlaying = false;
  subscribe((next) => {
    if (next.trackId === paintedId && next.playing === paintedPlaying) return;
    paintedId = next.trackId;
    paintedPlaying = next.playing;
    paintRows();
  });
}
