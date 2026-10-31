/**
 * Labels and the track-list sort.
 *
 * These read the numbers and strings the page already has. They do not
 * fetch, and they do not write the library.
 */

import type { Track } from "./api-types";
import { formatDate, formatNumber, getLocale, PSEUDO, t } from "./i18n";
import { state } from "./state";

/**
 * Format a track length in milliseconds as m:ss.
 *
 * The list column uses a short label so a virtualized row stays one line.
 * Empty input stays blank. No library request is made.
 *
 * @param {number|string|null|undefined} ms Length in milliseconds.
 * @returns {string} Minutes and zero-padded seconds, or an empty string.
 */
export function lengthLabel(ms: number | string | null | undefined) {
  if (ms == null || ms === "") return "";
  const total = Math.floor(Number(ms) / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Format a Unix timestamp for a history row.
 *
 * History stores seconds, while the Date constructor expects milliseconds.
 * An empty or unreadable stamp stays blank so the row does not show
 * "Invalid Date". No request is made.
 *
 * @param {number|string|null|undefined} stamp Seconds since the Unix epoch.
 * @returns {string} A short local date and time, or an empty string.
 */
export function clockLabel(stamp: number | string | null | undefined) {
  if (stamp == null || stamp === "") return "";
  const date = new Date(Number(stamp) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return formatDate(date, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/**
 * Format a total duration for the crate footer.
 *
 * Hours are included only when the total reaches one hour. The footer
 * uses this for the tracks currently in view. No request is made.
 *
 * @param {number|string} ms Total length in milliseconds.
 * @returns {string} A label such as "12m" or "1h 2m".
 */
export function durationLabel(ms: number | string | null | undefined) {
  const total = Math.round(Number(ms) / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return t("format.hoursMinutes", { hours, minutes });
  return t("format.minutes", { minutes });
}

/**
 * Format a byte count for the crate footer.
 *
 * Steps through KB, MB, and GB. A missing size is shown as zero bytes.
 * No request is made.
 *
 * @param {number|string|null|undefined} bytes File size in bytes.
 * @returns {string} A one-decimal size with its unit.
 */
export function sizeLabel(bytes: number | null | undefined) {
  const size = Number(bytes) || 0;
  if (size < 1024) return t("format.bytes", { count: size });
  const units = ["KB", "MB", "GB"];
  let amount = size / 1024;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${formatNumber(amount, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${units[unit]}`;
}

/**
 * Format a Serato color integer as a CSS hex color.
 *
 * White (0xffffff) means the crate or track has no color, so the swatch
 * is omitted. No request is made.
 *
 * @param {number|string|null|undefined} color Serato color integer.
 * @returns {string} A CSS color with a leading hash and six digits, or an empty string when there is no color.
 */
export function colorHex(color: number | string | null | undefined) {
  if (color == null || Number(color) === 0xffffff) return "";
  return `#${Number(color).toString(16).padStart(6, "0")}`;
}

/**
 * Compare two tracks for the current list sort.
 *
 * Numeric columns keep empty values after every real value. Text uses the
 * locale, with numbers compared as numbers, so "Track 2" stays before
 * "Track 10". Equal keys fall back to the id so the order is stable.
 * No request is made.
 *
 * @param {object} a First track or history row.
 * @param {object} b Second track or history row.
 * @returns {number} A negative, zero, or positive order for Array sort.
 */
export function compare(a: Track, b: Track) {
  const key = state.sort;
  const dir = state.sortDir;
  let av = a[key];
  let bv = b[key];
  if (key === "bpm" || key === "length_ms" || key === "start") {
    const an = av == null || av === "" ? null : Number(av);
    const bn = bv == null || bv === "" ? null : Number(bv);
    if (an == null && bn == null) return a.id - b.id;
    // Empty BPM, length, or start sorts after every real number.
    if (an == null) return 1;
    if (bn == null) return -1;
    if (an !== bn) return (an - bn) * dir;
    return a.id - b.id;
  }
  av = String(av || "").toLocaleLowerCase();
  bv = String(bv || "").toLocaleLowerCase();
  if (!av && bv) return 1;
  if (av && !bv) return -1;
  const locale = getLocale();
  const order = av.localeCompare(bv, locale === PSEUDO ? "en" : locale, { numeric: true, sensitivity: "base" });
  if (order !== 0) return order * dir;
  return a.id - b.id;
}
