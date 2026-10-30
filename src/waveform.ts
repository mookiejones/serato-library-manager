/**
 * Serato-style waveform math and offscreen tile rendering.
 *
 * `parseSwf1` reads the little-endian SWF1 body from `GET /api/waveform`.
 * Detail and overview points are six uint8 bands: low peak, low RMS, mid
 * peak, mid RMS, high peak, high RMS. 255 is full scale. Lows are under
 * 250 Hz, mids are 250 Hz to 4 kHz, and highs are over 4 kHz.
 *
 * Color is a blend of those bands: red for lows, green for mids, and blue
 * for highs. Peak is the outer layer. RMS is the brighter inner layer.
 * Tiles are painted once into pixel buffers and blitted while the playhead
 * stays at the center, so a long track does not redraw every point.
 *
 * Beat times follow the track route. Between two markers the spacing is
 * `(next.position_seconds - position_seconds) / beats`. After the last
 * marker the spacing is `60 / bpm`. The first marker is a downbeat.
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/** One parsed SWF1 body. Sections are copies, not views of the response. */
export interface ParsedWaveform {
  version: number;
  flags: number;
  analyzerVersion: number;
  sampleRate: number;
  pointsPerSecond: number;
  durationMs: number;
  detail: Uint8Array;
  overview: Uint8Array;
  serato: Uint8Array;
  detailCount: number;
  overviewCount: number;
  seratoColumns: number;
  seratoBands: number;
  lowHz: number;
  highHz: number;
}

/** One beatgrid marker from `GET /api/track`. */
export interface BeatgridMarker {
  positionSeconds: number;
  beats?: number;
  bpm?: number;
}

/** One beat to draw. Downbeats are the first marker and every fourth beat. */
export interface BeatTick {
  seconds: number;
  downbeat: boolean;
}

/** Cue, loop, and beatgrid marks drawn on the waveform. */
export interface WaveMarkers {
  cues: readonly WaveCue[];
  loops: readonly WaveLoop[];
  beatgrid: readonly BeatgridMarker[];
}

export interface WaveCue {
  seconds: number;
  color: string;
}

export interface WaveLoop {
  startSeconds: number;
  endSeconds: number;
  color: string;
}

export type OverviewSource =
  | { kind: "computed"; points: Uint8Array; count: number }
  | { kind: "serato"; columns: readonly (readonly number[])[] };

/** CSS pixels in one offscreen detail tile. */
export const TILE_CSS_WIDTH = 256;

/** Default zoom. CSS pixels per second of audio. */
export const ZOOM_DEFAULT_PPS = 80;

/** Furthest zoom out. */
export const ZOOM_MIN_PPS = 10;

/** Closest zoom in. */
export const ZOOM_MAX_PPS = 320;

/** Each zoom step multiplies or divides the pixels per second by this. */
export const ZOOM_FACTOR = 1.25;

/**
 * Warm-frame draw budget in milliseconds.
 *
 * A frame blits the visible tiles. It does not walk the whole track.
 */
export const FRAME_BUDGET_MS = 16;

/** Walnut well behind the waveform. Matches `--color-bg`. */
export const WAVE_BG: Rgb = { r: 0x23, g: 0x19, b: 0x10 };

/** Peak fringe mixed over the well. The RMS core is opaque. */
export const OUTER_ALPHA = 0.6;

/** Played overview columns are multiplied by this. */
export const PLAYED_SHADE = 0.45;

/** Regular beat ticks are this fraction of the canvas height, at each edge. */
export const BEAT_HEIGHT_RATIO = 0.12;

/** Downbeats extend a little farther than the other beats. */
export const DOWNBEAT_HEIGHT_RATIO = 0.18;

/** White mixed over the waveform for a regular beat. */
export const BEAT_ALPHA = 0.28;

/** Downbeats use a slightly stronger white. */
export const DOWNBEAT_ALPHA = 0.35;

/** Seek-bar primary, used when a marker has no usable color. */
export const DEFAULT_MARKER_COLOR: Rgb = { r: 0xe2, g: 0x3b, b: 0x16 };

/** Playhead on the zoomed view and the overview. */
export const PLAYHEAD_COLOR: Rgb = { r: 0xe2, g: 0x3b, b: 0x16 };

const BEAT_MARK: Rgb = { r: 255, g: 255, b: 255 };
const HEADER_BYTES = 64;
const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
const MAX_POINTS = 20_000_000;
const MAX_TICKS = 8192;

/**
 * Read an SWF1 body.
 *
 * The layout is the 64-byte little-endian header, then `N * 6` detail
 * bytes, `M * 6` overview bytes, and `S * bands` Serato Overview bytes.
 * A wrong magic, a header size other than 64, or a body whose length
 * does not match the counts returns null. Nothing is fetched.
 *
 * @param input Response bytes.
 * @returns The parsed sections, or null when the body is not SWF1.
 */
export function parseSwf1(input: ArrayBuffer | Uint8Array): ParsedWaveform | null {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (bytes.byteLength < HEADER_BYTES) return null;
  if (bytes[0] !== 0x53 || bytes[1] !== 0x57 || bytes[2] !== 0x46 || bytes[3] !== 0x31) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint16(4, true) !== HEADER_BYTES) return null;
  const version = view.getUint16(6, true);
  const flags = view.getUint16(8, true);
  const analyzerVersion = view.getUint16(10, true);
  const sampleRate = view.getUint32(12, true);
  const detailHzMilli = view.getUint32(16, true);
  const durationMs = view.getUint32(20, true);
  const detailCount = view.getUint32(24, true);
  const overviewCount = view.getUint32(28, true);
  const seratoColumns = view.getUint32(32, true);
  const seratoBands = view.getUint16(36, true);
  const lowHzMilli = view.getUint32(40, true);
  const highHzMilli = view.getUint32(44, true);
  if (detailCount > MAX_POINTS || overviewCount > MAX_POINTS || seratoColumns > MAX_POINTS) return null;
  const detailBytes = detailCount * 6;
  const overviewBytes = overviewCount * 6;
  const seratoBytes = seratoColumns * seratoBands;
  if (!Number.isSafeInteger(detailBytes + overviewBytes + seratoBytes)) return null;
  const end = HEADER_BYTES + detailBytes + overviewBytes + seratoBytes;
  if (end !== bytes.byteLength) return null;
  let offset = HEADER_BYTES;
  const detail = bytes.slice(offset, offset + detailBytes);
  offset += detailBytes;
  const overview = bytes.slice(offset, offset + overviewBytes);
  offset += overviewBytes;
  const serato = bytes.slice(offset, offset + seratoBytes);
  return {
    version,
    flags,
    analyzerVersion,
    sampleRate,
    pointsPerSecond: detailHzMilli / 1000,
    durationMs,
    detail,
    overview,
    serato,
    detailCount,
    overviewCount,
    seratoColumns,
    seratoBands,
    lowHz: lowHzMilli / 1000,
    highHz: highHzMilli / 1000,
  };
}

/**
 * Blend low, mid, and high into one RGB color.
 *
 * The hue follows the loudest bands: a pure low is red, a pure mid is
 * green, and a pure high is blue. Quiet and loud copies of the same mix
 * share a hue. Height is separate, from `bandLevel`. Values outside 0 to
 * 255 are clamped. A silent mix is black.
 *
 * @param low Low-band amplitude, 0 to 255.
 * @param mid Mid-band amplitude, 0 to 255.
 * @param high High-band amplitude, 0 to 255.
 * @returns The blended color.
 */
export function bandColor(low: number, mid: number, high: number): Rgb {
  const l = clamp255(low);
  const m = clamp255(mid);
  const h = clamp255(high);
  const max = Math.max(l, m, h);
  if (max === 0) return { r: 0, g: 0, b: 0 };
  return {
    r: Math.round((l / max) * 255),
    g: Math.round((m / max) * 255),
    b: Math.round((h / max) * 255),
  };
}

/**
 * Amplitude of one three-band sample, from 0 to 1.
 *
 * The loudest band sets the height. A non-finite number counts as silence.
 *
 * @param low Low-band amplitude.
 * @param mid Mid-band amplitude.
 * @param high High-band amplitude.
 * @returns Full scale at 1.
 */
export function bandLevel(low: number, mid: number, high: number): number {
  return Math.max(clamp255(low), clamp255(mid), clamp255(high)) / 255;
}

/**
 * Collapse one Serato Overview column into low, mid, and high.
 *
 * The tag stores 16 bands from low to high. Bands 0 through 4 are low,
 * 5 through 10 are mid, and 11 through 15 are high. Each group keeps its
 * loudest band. A short column leaves the missing groups at 0.
 *
 * @param column Sixteen uint8 bands, low first.
 * @returns Group peaks from 0 to 255.
 */
export function seratoColumnLevels(column: readonly number[]): { low: number; mid: number; high: number } {
  let low = 0;
  let mid = 0;
  let high = 0;
  const count = Math.min(column.length, 16);
  for (let index = 0; index < count; index += 1) {
    const value = clamp255(column[index] ?? 0);
    if (index <= 4) low = Math.max(low, value);
    else if (index <= 10) mid = Math.max(mid, value);
    else high = Math.max(high, value);
  }
  return { low, mid, high };
}

/**
 * Beat ticks inside a half-open time window.
 *
 * Markers are ordered by `positionSeconds`. Between two markers the
 * spacing is the gap divided by `beats`, and that many ticks are emitted
 * starting at the marker, not including the next marker. After the last
 * marker the spacing is `60 / bpm`. The first marker is beat 0, a
 * downbeat, and every fourth beat after it is a downbeat. Ticks before
 * the first marker are not invented. A segment that would emit more than
 * 8192 ticks is skipped. `endSeconds` is exclusive.
 *
 * @param markers Beatgrid from `GET /api/track`.
 * @param startSeconds First time that may be included.
 * @param endSeconds First time that is excluded.
 * @returns Ticks in time order. Empty when the window or the grid is unusable.
 */
export function beatgridTicks(
  markers: readonly BeatgridMarker[],
  startSeconds: number,
  endSeconds: number,
): BeatTick[] {
  if (!Number.isFinite(startSeconds) || !Number.isFinite(endSeconds) || endSeconds <= startSeconds) return [];
  const ordered = markers.filter((marker) => Number.isFinite(marker.positionSeconds)).slice();
  ordered.sort((left, right) => left.positionSeconds - right.positionSeconds);
  if (ordered.length === 0) return [];
  const ticks: BeatTick[] = [];
  let beatIndex = 0;
  for (let index = 0; index < ordered.length; index += 1) {
    const marker = ordered[index];
    if (!marker) continue;
    const next = ordered[index + 1];
    if (next) {
      const beats = marker.beats;
      if (beats === undefined || !Number.isFinite(beats) || beats < 1) continue;
      const count = Math.round(beats);
      const spacing = (next.positionSeconds - marker.positionSeconds) / beats;
      if (!(spacing > 0) || count < 1) continue;
      pushRange(ticks, marker.positionSeconds, spacing, beatIndex, count, startSeconds, endSeconds);
      beatIndex += count;
      continue;
    }
    const bpm = marker.bpm;
    if (bpm === undefined || !Number.isFinite(bpm) || bpm <= 0) continue;
    const spacing = 60 / bpm;
    if (!(spacing > 0)) continue;
    const first = Math.max(0, Math.ceil((startSeconds - marker.positionSeconds) / spacing - 1e-9));
    const lastExclusive = Math.ceil((endSeconds - marker.positionSeconds) / spacing - 1e-9);
    if (lastExclusive <= first) continue;
    const emit = Math.min(lastExclusive, first + MAX_TICKS);
    pushRange(ticks, marker.positionSeconds, spacing, beatIndex, emit, startSeconds, endSeconds, first);
  }
  return ticks;
}

/**
 * Map a time to a CSS x with the playhead fixed at the center.
 *
 * Zoom is `pixelsPerSecond`. A larger value moves a neighboring time
 * farther from the center. A non-positive zoom or a non-finite time
 * stays on the center.
 *
 * @param timeSeconds Time to place.
 * @param playheadSeconds Time pinned to the center.
 * @param pixelsPerSecond CSS pixels per second.
 * @param width CSS width of the view.
 * @returns The x coordinate. May lie outside the view.
 */
export function timeToX(
  timeSeconds: number,
  playheadSeconds: number,
  pixelsPerSecond: number,
  width: number,
): number {
  if (!(pixelsPerSecond > 0) || !Number.isFinite(timeSeconds) || !Number.isFinite(playheadSeconds) || !Number.isFinite(width)) {
    return width / 2;
  }
  return width / 2 + (timeSeconds - playheadSeconds) * pixelsPerSecond;
}

/**
 * Map a CSS x back to a time. The inverse of `timeToX`.
 *
 * @param x CSS x in the zoomed view.
 * @param playheadSeconds Time pinned to the center.
 * @param pixelsPerSecond CSS pixels per second.
 * @param width CSS width of the view.
 * @returns The time in seconds.
 */
export function xToTime(x: number, playheadSeconds: number, pixelsPerSecond: number, width: number): number {
  if (!(pixelsPerSecond > 0) || !Number.isFinite(x) || !Number.isFinite(playheadSeconds) || !Number.isFinite(width)) {
    return playheadSeconds;
  }
  return playheadSeconds + (x - width / 2) / pixelsPerSecond;
}

/**
 * Map a time onto the full-track overview.
 *
 * The start is 0 and the end is the duration. A missing duration returns 0.
 *
 * @param timeSeconds Time to place.
 * @param durationSeconds Length of the track.
 * @param width CSS or device width. The caller chooses the unit.
 * @returns The x coordinate.
 */
export function overviewTimeToX(timeSeconds: number, durationSeconds: number, width: number): number {
  if (!(durationSeconds > 0) || !(width > 0) || !Number.isFinite(timeSeconds)) return 0;
  return (timeSeconds / durationSeconds) * width;
}

/**
 * Map an overview x to a time, clamped to the track.
 *
 * @param x X in the same unit as `width`.
 * @param width Width of the overview.
 * @param durationSeconds Length of the track.
 * @returns Seconds from 0 through the duration.
 */
export function overviewXToTime(x: number, width: number, durationSeconds: number): number {
  if (!(width > 0) || !(durationSeconds > 0) || !Number.isFinite(x)) return 0;
  const ratio = Math.min(1, Math.max(0, x / width));
  return ratio * durationSeconds;
}

/**
 * Step the zoom in or out, clamped to the min and max.
 *
 * A positive direction zooms in. The result is not rounded, so repeated
 * steps return to the value they left.
 *
 * @param current CSS pixels per second.
 * @param direction 1 zooms in. -1 zooms out.
 * @returns The next pixels per second.
 */
export function zoomPixelsPerSecond(current: number, direction: 1 | -1): number {
  const base = Number.isFinite(current) && current > 0 ? current : ZOOM_DEFAULT_PPS;
  const next = base * (direction > 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR);
  if (next >= ZOOM_MAX_PPS) return ZOOM_MAX_PPS;
  if (next <= ZOOM_MIN_PPS) return ZOOM_MIN_PPS;
  return next;
}

/**
 * Device-pixel width of one detail tile.
 *
 * @param dpr `devicePixelRatio`. A missing or non-positive value uses 1.
 * @returns The tile width in device pixels.
 */
export function tileDeviceWidth(dpr: number): number {
  const scale = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
  return Math.max(1, Math.round(TILE_CSS_WIDTH * scale));
}

/**
 * Parse `#` hex into RGB.
 *
 * Three, six, and eight digit forms are accepted. An eight digit form
 * keeps the first six. Anything else returns null.
 *
 * @param value Color from a cue or a loop.
 * @returns The color, or null when it is not a `#` hex string.
 */
export function colorFromHex(value: string): Rgb | null {
  if (!HEX_COLOR.test(value)) return null;
  let hex = value.slice(1);
  if (hex.length === 3) {
    const r = hex[0] ?? "";
    const g = hex[1] ?? "";
    const b = hex[2] ?? "";
    hex = `${r}${r}${g}${g}${b}${b}`;
  }
  if (hex.length === 8) hex = hex.slice(0, 6);
  const parsed = Number.parseInt(hex, 16);
  if (!Number.isFinite(parsed)) return null;
  return { r: (parsed >> 16) & 255, g: (parsed >> 8) & 255, b: parsed & 255 };
}

/**
 * Turn track-route beatgrid rows into marker records.
 *
 * `position_seconds` is the stored float. A finite numeric `position` is
 * used only when that field is missing. A non-finite row is dropped.
 * `beats` and `bpm` are copied when they are finite numbers.
 *
 * @param rows `beatgrid` from `GET /api/track`.
 * @returns Markers in the order given.
 */
export function beatgridFromMarkers(
  rows: readonly {
    position_seconds?: number;
    position?: number | string | null;
    beats?: number | string | null;
    bpm?: number | string | null;
  }[] | undefined,
): BeatgridMarker[] {
  if (!rows || rows.length === 0) return [];
  const found: BeatgridMarker[] = [];
  for (const row of rows) {
    const position = finiteNumber(row.position_seconds) ?? finiteNumber(row.position);
    if (position === null) continue;
    const marker: BeatgridMarker = { positionSeconds: position };
    const beats = finiteNumber(row.beats);
    const bpm = finiteNumber(row.bpm);
    if (beats !== null) marker.beats = beats;
    if (bpm !== null) marker.bpm = bpm;
    found.push(marker);
  }
  return found;
}

/**
 * Turn track-route loop rows into spans.
 *
 * A row needs a finite start and an end after that start. The color is
 * kept as stored. An empty color is drawn with the default marker color.
 *
 * @param rows `loops` from `GET /api/track`.
 * @returns Spans in the order given.
 */
export function loopsFromMarkers(
  rows: readonly {
    start_ms?: number | string;
    end_ms?: number | string;
    color?: string;
  }[] | undefined,
): WaveLoop[] {
  if (!rows || rows.length === 0) return [];
  const found: WaveLoop[] = [];
  for (const row of rows) {
    const start = finiteNumber(row.start_ms);
    const end = finiteNumber(row.end_ms);
    if (start === null || end === null || end <= start || start < 0) continue;
    found.push({
      startSeconds: start / 1000,
      endSeconds: end / 1000,
      color: typeof row.color === "string" ? row.color : "",
    });
  }
  return found;
}

/**
 * Cache of offscreen detail tiles for one track.
 *
 * A frame blits the tiles under the view and draws markers in screen
 * space. Tile generation reports how many detail points it read. A warm
 * frame reads none.
 */
export class DetailTiles {
  private readonly tiles = new Map<string, Uint8ClampedArray>();
  private blank: Uint8ClampedArray | null = null;

  /**
   * Remember one detail buffer.
   *
   * @param detail `N * 6` uint8 bytes.
   * @param pointCount N.
   * @param pointsPerSecond Detail rate from the header. 150 in SWF1.
   */
  constructor(
    private readonly detail: Uint8Array,
    private readonly pointCount: number,
    private readonly pointsPerSecond: number,
  ) {}

  /**
   * Drop cached tiles.
   *
   * Called when the zoom changes so the next frame rebuilds at the new scale.
   */
  clear(): void {
    this.tiles.clear();
  }

  /**
   * Paint one zoomed frame into `frame`.
   *
   * The playhead is the center column. Tiles outside the view, plus one
   * tile of margin, are not generated. Markers are cues, shaded loops, and
   * beat ticks. Downbeats are taller.
   *
   * @param frame RGBA buffer of `width * height`.
   * @param width Device pixels.
   * @param height Device pixels.
   * @param dpr Device pixel ratio.
   * @param playheadSeconds Audio position.
   * @param pixelsPerSecond CSS pixels per second.
   * @param markers Cues, loops, and the beatgrid. Beat ticks are not drawn
   *   when the grid is empty.
   * @returns How many detail points this call sampled. Zero when every
   *   visible tile was already cached.
   */
  paint(
    frame: Uint8ClampedArray,
    width: number,
    height: number,
    dpr: number,
    playheadSeconds: number,
    pixelsPerSecond: number,
    markers: WaveMarkers,
  ): { pointsRead: number } {
    const scale = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
    const pps = pixelsPerSecond > 0 ? pixelsPerSecond : ZOOM_DEFAULT_PPS;
    this.ensureBlank(width, height);
    const blank = this.blank;
    if (!blank || frame.length !== blank.length) return { pointsRead: 0 };
    frame.set(blank);
    const cssWidth = width / scale;
    const tileSeconds = TILE_CSS_WIDTH / pps;
    const tileWidth = tileDeviceWidth(scale);
    const viewStart = playheadSeconds - cssWidth / 2 / pps;
    const viewEnd = playheadSeconds + cssWidth / 2 / pps;
    const first = Math.floor(viewStart / tileSeconds) - 1;
    const last = Math.floor(viewEnd / tileSeconds) + 1;
    let pointsRead = 0;
    const needed = new Set<string>();
    for (let index = first; index <= last; index += 1) {
      const key = `${Math.round(pps * 1000)}|${scale}|${height}|${index}`;
      needed.add(key);
      let tile = this.tiles.get(key);
      if (!tile) {
        const rendered = renderTile(
          this.detail,
          this.pointCount,
          this.pointsPerSecond,
          index * tileSeconds,
          tileSeconds,
          tileWidth,
          height,
          scale,
        );
        tile = rendered.pixels;
        pointsRead += rendered.pointsRead;
        this.tiles.set(key, tile);
      }
      const left = timeToX(index * tileSeconds, playheadSeconds, pps, cssWidth) * scale;
      blit(frame, width, height, tile, tileWidth, Math.round(left));
    }
    if (this.tiles.size > 24) {
      for (const key of this.tiles.keys()) {
        if (!needed.has(key)) this.tiles.delete(key);
      }
    }
    drawLoops(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.loops);
    drawBeats(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.beatgrid, viewStart, viewEnd);
    drawCues(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.cues);
    drawPlayhead(frame, width, height);
    return { pointsRead };
  }

  private ensureBlank(width: number, height: number): void {
    const count = width * height * 4;
    if (this.blank && this.blank.length === count) return;
    const blank = new Uint8ClampedArray(count);
    fillBackground(blank);
    this.blank = blank;
  }
}

/**
 * Paint the full-track overview into a new buffer.
 *
 * Computed points use peak and RMS. Serato columns use the 16-band
 * grouping and one solid level. The buffer is unshaded. The caller copies
 * it and shades the played portion.
 *
 * @param source Computed overview bytes or Serato columns.
 * @param width Device pixels.
 * @param height Device pixels.
 * @returns RGBA pixels.
 */
export function renderOverview(source: OverviewSource, width: number, height: number): Uint8ClampedArray {
  const pixels = new Uint8ClampedArray(width * height * 4);
  fillBackground(pixels);
  const columns = source.kind === "computed" ? source.count : source.columns.length;
  if (columns < 1 || width < 1 || height < 1) return pixels;
  for (let x = 0; x < width; x += 1) {
    const start = Math.floor((x / width) * columns);
    const end = Math.max(start + 1, Math.floor(((x + 1) / width) * columns));
    let lowPeak = 0;
    let lowRms = 0;
    let midPeak = 0;
    let midRms = 0;
    let highPeak = 0;
    let highRms = 0;
    for (let index = start; index < end && index < columns; index += 1) {
      if (source.kind === "computed") {
        const offset = index * 6;
        lowPeak = Math.max(lowPeak, source.points[offset] ?? 0);
        lowRms = Math.max(lowRms, source.points[offset + 1] ?? 0);
        midPeak = Math.max(midPeak, source.points[offset + 2] ?? 0);
        midRms = Math.max(midRms, source.points[offset + 3] ?? 0);
        highPeak = Math.max(highPeak, source.points[offset + 4] ?? 0);
        highRms = Math.max(highRms, source.points[offset + 5] ?? 0);
      } else {
        const levels = seratoColumnLevels(source.columns[index] ?? []);
        lowPeak = Math.max(lowPeak, levels.low);
        midPeak = Math.max(midPeak, levels.mid);
        highPeak = Math.max(highPeak, levels.high);
        lowRms = lowPeak;
        midRms = midPeak;
        highRms = highPeak;
      }
    }
    paintColumn(pixels, x, width, height, 0, lowPeak, lowRms, midPeak, midRms, highPeak, highRms);
  }
  return pixels;
}

/**
 * Darken the played portion of an overview buffer.
 *
 * Columns before `playedX` are multiplied by `PLAYED_SHADE`. The unplayed
 * side is left as rendered. The buffer is modified.
 *
 * @param pixels RGBA overview frame.
 * @param width Device pixels.
 * @param height Device pixels.
 * @param playedX First unplayed device column.
 */
export function shadePlayed(pixels: Uint8ClampedArray, width: number, height: number, playedX: number): void {
  const end = Math.max(0, Math.min(width, Math.round(playedX)));
  for (let y = 0; y < height; y += 1) {
    const row = y * width;
    for (let x = 0; x < end; x += 1) {
      const offset = (row + x) * 4;
      pixels[offset] = Math.round((pixels[offset] ?? 0) * PLAYED_SHADE);
      pixels[offset + 1] = Math.round((pixels[offset + 1] ?? 0) * PLAYED_SHADE);
      pixels[offset + 2] = Math.round((pixels[offset + 2] ?? 0) * PLAYED_SHADE);
    }
  }
}

/**
 * Draw overview cues, shaded loops, and the playhead onto a frame.
 *
 * Beat ticks are not drawn here. They belong on the zoomed view.
 * Coordinates are device pixels across the whole track.
 *
 * @param pixels RGBA overview frame.
 * @param width Device pixels.
 * @param height Device pixels.
 * @param durationSeconds Track length used to place markers.
 * @param playheadSeconds Audio position.
 * @param markers Cues and loops. The beatgrid is ignored.
 */
export function drawOverviewMarks(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  durationSeconds: number,
  playheadSeconds: number,
  markers: WaveMarkers,
): void {
  if (!(durationSeconds > 0) || width < 1) return;
  const xOf = (seconds: number) => (seconds / durationSeconds) * width;
  drawLoops(pixels, width, height, 1, 0, 1, width, markers.loops, xOf);
  drawCues(pixels, width, height, 1, 0, 1, width, markers.cues, xOf);
  const playX = Math.round(Math.min(width - 1, Math.max(0, xOf(playheadSeconds))));
  fillSpan(pixels, width, height, playX, playX + 1, 0, height, PLAYHEAD_COLOR, 1);
}

function renderTile(
  detail: Uint8Array,
  pointCount: number,
  pointsPerSecond: number,
  startSeconds: number,
  tileSeconds: number,
  width: number,
  height: number,
  dpr: number,
): { pixels: Uint8ClampedArray; pointsRead: number } {
  const pixels = new Uint8ClampedArray(width * height * 4);
  fillBackground(pixels);
  let pointsRead = 0;
  const rate = pointsPerSecond > 0 ? pointsPerSecond : 150;
  for (let x = 0; x < width; x += 1) {
    const t0 = startSeconds + (x / width) * tileSeconds;
    const t1 = startSeconds + ((x + 1) / width) * tileSeconds;
    let i0 = Math.floor(t0 * rate);
    let i1 = Math.ceil(t1 * rate);
    if (i1 <= i0) i1 = i0 + 1;
    if (i0 < 0) i0 = 0;
    if (i1 > pointCount) i1 = pointCount;
    if (i0 >= i1) continue;
    let lowPeak = 0;
    let lowRms = 0;
    let midPeak = 0;
    let midRms = 0;
    let highPeak = 0;
    let highRms = 0;
    for (let index = i0; index < i1; index += 1) {
      pointsRead += 1;
      const offset = index * 6;
      lowPeak = Math.max(lowPeak, detail[offset] ?? 0);
      lowRms = Math.max(lowRms, detail[offset + 1] ?? 0);
      midPeak = Math.max(midPeak, detail[offset + 2] ?? 0);
      midRms = Math.max(midRms, detail[offset + 3] ?? 0);
      highPeak = Math.max(highPeak, detail[offset + 4] ?? 0);
      highRms = Math.max(highRms, detail[offset + 5] ?? 0);
    }
    paintColumn(pixels, x, width, height, 0, lowPeak, lowRms, midPeak, midRms, highPeak, highRms);
  }
  return { pixels, pointsRead };
}

/**
 * Paint one waveform column.
 *
 * Peak sets the outer height and is mixed with `OUTER_ALPHA`. RMS sets
 * the inner height and is opaque. Both use `bandColor`.
 *
 * @param pixels RGBA buffer.
 * @param x Column.
 * @param width Buffer width.
 * @param height Buffer height.
 * @param gutter Top rows left for beat ticks.
 * @param lowPeak Low peak.
 * @param lowRms Low RMS.
 * @param midPeak Mid peak.
 * @param midRms Mid RMS.
 * @param highPeak High peak.
 * @param highRms High RMS.
 */
export function paintColumn(
  pixels: Uint8ClampedArray,
  x: number,
  width: number,
  height: number,
  gutter: number,
  lowPeak: number,
  lowRms: number,
  midPeak: number,
  midRms: number,
  highPeak: number,
  highRms: number,
): void {
  const peakLevel = bandLevel(lowPeak, midPeak, highPeak);
  const rmsLevel = bandLevel(lowRms, midRms, highRms);
  if (peakLevel <= 0 && rmsLevel <= 0) return;
  const top = Math.min(gutter, height - 1);
  const bandHeight = height - top;
  const mid = top + (bandHeight - 1) / 2;
  const peakHalf = Math.max(peakLevel > 0 ? 0.5 : 0, peakLevel * (bandHeight / 2) * 0.92);
  const rmsHalf = rmsLevel * (bandHeight / 2) * 0.92;
  const y0 = Math.max(top, Math.floor(mid - Math.max(peakHalf, rmsHalf)));
  const y1 = Math.min(height - 1, Math.ceil(mid + Math.max(peakHalf, rmsHalf)));
  const peakColor = bandColor(lowPeak, midPeak, highPeak);
  const rmsColor = bandColor(lowRms, midRms, highRms);
  for (let y = y0; y <= y1; y += 1) {
    const fromMid = Math.abs(y - mid);
    const inner = rmsLevel > 0 && fromMid <= rmsHalf;
    const outer = peakLevel > 0 && fromMid <= peakHalf;
    if (!inner && !outer) continue;
    const color = inner ? rmsColor : peakColor;
    const alpha = inner ? 1 : OUTER_ALPHA;
    blendPixel(pixels, width, x, y, color, alpha);
  }
}

function drawLoops(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  dpr: number,
  playheadSeconds: number,
  pixelsPerSecond: number,
  cssWidth: number,
  loops: readonly WaveLoop[],
  xOf?: (seconds: number) => number,
): void {
  for (const loop of loops) {
    const color = colorFromHex(loop.color) ?? DEFAULT_MARKER_COLOR;
    const start = xOf
      ? xOf(loop.startSeconds)
      : timeToX(loop.startSeconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
    const end = xOf
      ? xOf(loop.endSeconds)
      : timeToX(loop.endSeconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
    const left = Math.min(start, end);
    const right = Math.max(start, end);
    fillSpan(pixels, width, height, Math.floor(left), Math.ceil(right), 0, height, color, 0.35);
    const edge = Math.max(1, Math.round(dpr));
    fillSpan(pixels, width, height, Math.round(left), Math.round(left) + edge, 0, height, color, 1);
    fillSpan(pixels, width, height, Math.round(right) - edge, Math.round(right), 0, height, color, 1);
  }
}

function drawCues(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  dpr: number,
  playheadSeconds: number,
  pixelsPerSecond: number,
  cssWidth: number,
  cues: readonly WaveCue[],
  xOf?: (seconds: number) => number,
): void {
  const edge = Math.max(1, Math.round(2 * dpr));
  for (const cue of cues) {
    const color = colorFromHex(cue.color) ?? DEFAULT_MARKER_COLOR;
    const x = xOf
      ? xOf(cue.seconds)
      : timeToX(cue.seconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
    fillSpan(pixels, width, height, Math.round(x) - Math.floor(edge / 2), Math.round(x) - Math.floor(edge / 2) + edge, 0, height, color, 1);
  }
}

function drawBeats(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  dpr: number,
  playheadSeconds: number,
  pixelsPerSecond: number,
  cssWidth: number,
  markers: readonly BeatgridMarker[],
  viewStart: number,
  viewEnd: number,
): void {
  const ticks = beatgridTicks(markers, viewStart, viewEnd);
  const tickWidth = Math.max(1, Math.round(dpr));
  const regularHeight = Math.max(1, Math.round(height * BEAT_HEIGHT_RATIO));
  const downbeatHeight = Math.max(regularHeight + 1, Math.round(height * DOWNBEAT_HEIGHT_RATIO));
  for (const tick of ticks) {
    const x = Math.round(timeToX(tick.seconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr);
    const tickHeight = Math.min(tick.downbeat ? downbeatHeight : regularHeight, Math.floor(height / 2) - 1);
    if (tickHeight < 1) continue;
    const alpha = tick.downbeat ? DOWNBEAT_ALPHA : BEAT_ALPHA;
    fillSpan(pixels, width, height, x, x + tickWidth, 0, tickHeight, BEAT_MARK, alpha);
    fillSpan(pixels, width, height, x, x + tickWidth, height - tickHeight, height, BEAT_MARK, alpha);
  }
}

function drawPlayhead(pixels: Uint8ClampedArray, width: number, height: number): void {
  const x = Math.floor(width / 2);
  fillSpan(pixels, width, height, x, x + 2, 0, height, PLAYHEAD_COLOR, 1);
}

function fillSpan(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  x0: number,
  x1: number,
  y0: number,
  y1: number,
  color: Rgb,
  alpha: number,
): void {
  const left = Math.max(0, x0);
  const right = Math.min(width, x1);
  const top = Math.max(0, y0);
  const bottom = Math.min(height, y1);
  for (let x = left; x < right; x += 1) {
    for (let y = top; y < bottom; y += 1) blendPixel(pixels, width, x, y, color, alpha);
  }
}

function blendPixel(pixels: Uint8ClampedArray, width: number, x: number, y: number, color: Rgb, alpha: number): void {
  const offset = (y * width + x) * 4;
  const keep = 1 - alpha;
  pixels[offset] = Math.round(color.r * alpha + (pixels[offset] ?? 0) * keep);
  pixels[offset + 1] = Math.round(color.g * alpha + (pixels[offset + 1] ?? 0) * keep);
  pixels[offset + 2] = Math.round(color.b * alpha + (pixels[offset + 2] ?? 0) * keep);
  pixels[offset + 3] = 255;
}

function fillBackground(pixels: Uint8ClampedArray): void {
  for (let index = 0; index < pixels.length; index += 4) {
    pixels[index] = WAVE_BG.r;
    pixels[index + 1] = WAVE_BG.g;
    pixels[index + 2] = WAVE_BG.b;
    pixels[index + 3] = 255;
  }
}

function blit(
  dest: Uint8ClampedArray,
  destWidth: number,
  destHeight: number,
  src: Uint8ClampedArray,
  srcWidth: number,
  destX: number,
): void {
  let srcX = 0;
  let copyWidth = srcWidth;
  let dx = destX;
  if (dx < 0) {
    srcX = -dx;
    copyWidth -= srcX;
    dx = 0;
  }
  if (dx + copyWidth > destWidth) copyWidth = destWidth - dx;
  if (copyWidth <= 0) return;
  for (let y = 0; y < destHeight; y += 1) {
    const srcStart = (y * srcWidth + srcX) * 4;
    const destStart = (y * destWidth + dx) * 4;
    dest.set(src.subarray(srcStart, srcStart + copyWidth * 4), destStart);
  }
}

function pushRange(
  ticks: BeatTick[],
  origin: number,
  spacing: number,
  beatIndex: number,
  count: number,
  startSeconds: number,
  endSeconds: number,
  first = 0,
): void {
  const begin = Math.max(first, Math.ceil((startSeconds - origin) / spacing - 1e-9));
  for (let index = begin; index < count; index += 1) {
    const seconds = origin + index * spacing;
    if (seconds < startSeconds - 1e-6) continue;
    if (seconds >= endSeconds - 1e-9) break;
    if (ticks.length >= MAX_TICKS) return;
    ticks.push({ seconds, downbeat: (beatIndex + index) % 4 === 0 });
  }
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string" || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clamp255(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value <= 0) return 0;
  if (value >= 255) return 255;
  return value;
}
