/**
 * SWF1 parsing, band color, beatgrid ticks, zoom mapping, and frame cost.
 *
 * The 60-minute buffer is synthetic. No library file is opened.
 */

import { describe, expect, it } from "vitest";
import {
  DetailTiles,
  FRAME_BUDGET_MS,
  ZOOM_DEFAULT_PPS,
  ZOOM_MAX_PPS,
  ZOOM_MIN_PPS,
  bandColor,
  beatgridFromMarkers,
  beatgridTicks,
  loopsFromMarkers,
  overviewTimeToX,
  overviewXToTime,
  paintColumn,
  parseSwf1,
  seratoColumnLevels,
  shadePlayed,
  tileDeviceWidth,
  timeToX,
  xToTime,
  zoomPixelsPerSecond,
  type WaveMarkers,
} from "./waveform";

function encodeSwf1(detail: number[], overview: number[], serato: number[], seratoBands = serato.length > 0 ? 16 : 0): Uint8Array {
  const detailBytes = new Uint8Array(detail);
  const overviewBytes = new Uint8Array(overview);
  const seratoBytes = new Uint8Array(serato);
  const body = new Uint8Array(64 + detailBytes.length + overviewBytes.length + seratoBytes.length);
  body.set([0x53, 0x57, 0x46, 0x31], 0);
  const view = new DataView(body.buffer);
  view.setUint16(4, 64, true);
  view.setUint16(6, 1, true);
  let flags = 0;
  if (detailBytes.length > 0) flags |= 1;
  if (overviewBytes.length > 0) flags |= 2;
  if (seratoBytes.length > 0) flags |= 4;
  view.setUint16(8, flags, true);
  view.setUint16(10, 1, true);
  view.setUint32(12, 44100, true);
  view.setUint32(16, 150000, true);
  view.setUint32(20, 2000, true);
  view.setUint32(24, detailBytes.length / 6, true);
  view.setUint32(28, overviewBytes.length / 6, true);
  view.setUint32(32, seratoBands > 0 ? seratoBytes.length / seratoBands : 0, true);
  view.setUint16(36, seratoBands, true);
  view.setUint16(38, 0, true);
  view.setUint32(40, 250000, true);
  view.setUint32(44, 4_000_000, true);
  body.set(detailBytes, 64);
  body.set(overviewBytes, 64 + detailBytes.length);
  body.set(seratoBytes, 64 + detailBytes.length + overviewBytes.length);
  return body;
}

describe("parseSwf1", () => {
  it("reads the header and the three sections in order", () => {
    const detail = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    const overview = [20, 21, 22, 23, 24, 25];
    const serato = new Array(16).fill(0).map((_, index) => index + 1);
    const parsed = parseSwf1(encodeSwf1(detail, overview, serato));
    expect(parsed).not.toBeNull();
    expect(parsed?.version).toBe(1);
    expect(parsed?.sampleRate).toBe(44100);
    expect(parsed?.pointsPerSecond).toBe(150);
    expect(parsed?.durationMs).toBe(2000);
    expect(parsed?.lowHz).toBe(250);
    expect(parsed?.highHz).toBe(4000);
    expect(parsed?.detailCount).toBe(2);
    expect(parsed?.overviewCount).toBe(1);
    expect(parsed?.seratoColumns).toBe(1);
    expect(parsed?.seratoBands).toBe(16);
    expect(Array.from(parsed?.detail ?? [])).toEqual(detail);
    expect(Array.from(parsed?.overview ?? [])).toEqual(overview);
    expect(Array.from(parsed?.serato ?? [])).toEqual(serato);
    expect(parsed?.flags).toBe(7);
  });

  it("rejects a bad magic, a short body, a wrong header size, and a trailing byte", () => {
    expect(parseSwf1(new Uint8Array([1, 2, 3, 4]))).toBeNull();
    const body = encodeSwf1([1, 2, 3, 4, 5, 6], [], []);
    const badMagic = body.slice();
    badMagic[0] = 0x00;
    expect(parseSwf1(badMagic)).toBeNull();
    const badSize = body.slice();
    badSize[4] = 32;
    expect(parseSwf1(badSize)).toBeNull();
    expect(parseSwf1(body.slice(0, 20))).toBeNull();
    const extra = new Uint8Array(body.length + 1);
    extra.set(body);
    expect(parseSwf1(extra)).toBeNull();
  });
});

describe("band color", () => {
  it("maps lows to red, mids to green, and highs to blue", () => {
    expect(bandColor(255, 0, 0)).toEqual({ r: 255, g: 0, b: 0 });
    expect(bandColor(0, 200, 0)).toEqual({ r: 0, g: 255, b: 0 });
    expect(bandColor(0, 0, 10)).toEqual({ r: 0, g: 0, b: 255 });
  });

  it("keeps the hue of a quiet band and blends two bands", () => {
    expect(bandColor(12, 0, 0)).toEqual({ r: 255, g: 0, b: 0 });
    expect(bandColor(100, 100, 0)).toEqual({ r: 255, g: 255, b: 0 });
    expect(bandColor(0, 0, 0)).toEqual({ r: 0, g: 0, b: 0 });
    expect(bandColor(300, -5, 0)).toEqual({ r: 255, g: 0, b: 0 });
    expect(bandColor(Number.NaN, 0, 40)).toEqual({ r: 0, g: 0, b: 255 });
  });

  it("draws the peak as the outer layer and the RMS as the inner layer", () => {
    const height = 80;
    const pixels = new Uint8ClampedArray(height * 4);
    for (let index = 0; index < pixels.length; index += 4) {
      pixels[index] = 0x23;
      pixels[index + 1] = 0x19;
      pixels[index + 2] = 0x10;
      pixels[index + 3] = 255;
    }
    paintColumn(pixels, 0, 1, height, 0, 255, 0, 0, 80, 0, 0);
    const at = (y: number): number[] => {
      const offset = y * 4;
      return [pixels[offset] ?? 0, pixels[offset + 1] ?? 0, pixels[offset + 2] ?? 0];
    };
    expect(at(40)).toEqual([0, 255, 0]);
    expect(at(20)).toEqual([167, 10, 6]);
    expect(at(0)).toEqual([0x23, 0x19, 0x10]);
  });

  it("groups Serato Overview bands into low, mid, and high", () => {
    const low = new Array(16).fill(0);
    low[0] = 40;
    low[4] = 90;
    expect(seratoColumnLevels(low)).toEqual({ low: 90, mid: 0, high: 0 });
    const mid = new Array(16).fill(0);
    mid[5] = 10;
    mid[10] = 70;
    expect(seratoColumnLevels(mid)).toEqual({ low: 0, mid: 70, high: 0 });
    const high = new Array(16).fill(0);
    high[11] = 15;
    high[15] = 200;
    expect(seratoColumnLevels(high)).toEqual({ low: 0, mid: 0, high: 200 });
    expect(bandColor(90, 0, 0)).toEqual({ r: 255, g: 0, b: 0 });
    expect(bandColor(0, 0, 200)).toEqual({ r: 0, g: 0, b: 255 });
  });
});

describe("beatgrid ticks", () => {
  it("spaces beats between markers and after the last marker", () => {
    const ticks = beatgridTicks(
      [
        { positionSeconds: 0, beats: 4 },
        { positionSeconds: 2, bpm: 120 },
      ],
      0,
      4,
    );
    expect(ticks.map((tick) => [Number(tick.seconds.toFixed(3)), tick.downbeat])).toEqual([
      [0, true],
      [0.5, false],
      [1, false],
      [1.5, false],
      [2, true],
      [2.5, false],
      [3, false],
      [3.5, false],
    ]);
  });

  it("uses BPM on the last marker and does not invent beats before the grid", () => {
    const ticks = beatgridTicks(
      [
        { positionSeconds: 0, beats: 2 },
        { positionSeconds: 1, beats: 100, bpm: 60 },
      ],
      0,
      4,
    );
    expect(ticks.map((tick) => Number(tick.seconds.toFixed(3)))).toEqual([0, 0.5, 1, 2, 3]);
    expect(ticks[0]?.downbeat).toBe(true);
    expect(ticks[2]?.downbeat).toBe(false);
    expect(ticks[4]?.downbeat).toBe(true);
    const late = beatgridTicks([{ positionSeconds: 2, bpm: 60 }], 0, 5);
    expect(late.map((tick) => tick.seconds)).toEqual([2, 3, 4]);
  });

  it("drops a bad segment and keeps a later BPM", () => {
    const ticks = beatgridTicks(
      [
        { positionSeconds: 0, beats: 0 },
        { positionSeconds: Number.NaN, beats: 4 },
        { positionSeconds: 2, bpm: 120 },
      ],
      0,
      3,
    );
    expect(ticks.map((tick) => tick.seconds)).toEqual([2, 2.5]);
    expect(beatgridTicks([], 0, 10)).toEqual([]);
    expect(beatgridTicks([{ positionSeconds: 0, bpm: 120 }], 5, 5)).toEqual([]);
  });

  it("caps a tiny spacing instead of walking the whole window", () => {
    const ticks = beatgridTicks([{ positionSeconds: 0, bpm: 600_000 }], 0, 100);
    expect(ticks.length).toBeLessThanOrEqual(8192);
    expect(ticks.length).toBeGreaterThan(0);
  });

  it("reads position_seconds and loop ends from track rows", () => {
    expect(beatgridFromMarkers([
      { position: "0.000", position_seconds: 0.125, beats: 4 },
      { position: "1.000", position_seconds: 1.5, bpm: 174 },
      { position: "nope" },
    ])).toEqual([
      { positionSeconds: 0.125, beats: 4 },
      { positionSeconds: 1.5, bpm: 174 },
    ]);
    expect(loopsFromMarkers([
      { start_ms: 2000, end_ms: 8500, color: "#27AAE1" },
      { start_ms: 1000, end_ms: 1000, color: "#ffffff" },
      { start_ms: "bad", end_ms: 2000 },
    ])).toEqual([
      { startSeconds: 2, endSeconds: 8.5, color: "#27AAE1" },
    ]);
  });
});

describe("time to x", () => {
  it("keeps the playhead at the center and moves with the zoom", () => {
    expect(timeToX(10, 10, 80, 800)).toBe(400);
    expect(timeToX(11, 10, ZOOM_DEFAULT_PPS, 800)).toBe(480);
    expect(timeToX(11, 10, 160, 800)).toBe(560);
    expect(timeToX(11, 10, 40, 800)).toBe(440);
    expect(timeToX(9, 10, 80, 800)).toBe(320);
    expect(xToTime(560, 10, 160, 800)).toBe(11);
    expect(xToTime(440, 10, 40, 800)).toBe(11);
  });

  it("maps the overview across the whole track", () => {
    expect(overviewTimeToX(5, 20, 800)).toBe(200);
    expect(overviewXToTime(200, 800, 20)).toBe(5);
    expect(overviewXToTime(-10, 800, 20)).toBe(0);
    expect(overviewXToTime(5000, 800, 20)).toBe(20);
    expect(overviewXToTime(10, 0, 20)).toBe(0);
  });

  it("steps the zoom and stops at the ends", () => {
    expect(zoomPixelsPerSecond(80, 1)).toBe(100);
    expect(zoomPixelsPerSecond(100, -1)).toBe(80);
    expect(zoomPixelsPerSecond(ZOOM_MAX_PPS, 1)).toBe(ZOOM_MAX_PPS);
    expect(zoomPixelsPerSecond(ZOOM_MIN_PPS, -1)).toBe(ZOOM_MIN_PPS);
    expect(timeToX(11, 10, zoomPixelsPerSecond(80, 1), 800)).toBe(500);
    expect(tileDeviceWidth(1)).toBe(256);
    expect(tileDeviceWidth(2)).toBe(512);
  });
});

describe("beat ticks", () => {
  it("draws one-pixel edge marks, with a longer brighter downbeat", () => {
    const tiles = new DetailTiles(new Uint8Array(150 * 6), 150, 150);
    const width = 200;
    const height = 100;
    const frame = new Uint8ClampedArray(width * height * 4);
    tiles.paint(frame, width, height, 1, 1, 80, {
      cues: [{ seconds: 1.2, color: "#CC0000" }],
      loops: [{ startSeconds: 0.2, endSeconds: 0.4, color: "#27AAE1" }],
      beatgrid: [{ positionSeconds: 0, bpm: 120 }],
    });
    const at = (x: number, y: number): number[] => {
      const offset = (y * width + x) * 4;
      return [frame[offset] ?? 0, frame[offset + 1] ?? 0, frame[offset + 2] ?? 0, frame[offset + 3] ?? 0];
    };
    const background = [0x23, 0x19, 0x10, 255];
    expect(at(20, 0)).toEqual([112, 106, 100, 255]);
    expect(at(21, 0)).toEqual(background);
    expect(at(60, 0)).toEqual([97, 89, 83, 255]);
    expect(at(20, 15)).toEqual([112, 106, 100, 255]);
    expect(at(60, 15)).toEqual(background);
    expect(at(20, 50)).toEqual(background);
    expect(at(20, 99)).toEqual([112, 106, 100, 255]);
    expect(at(60, 99)).toEqual([97, 89, 83, 255]);
    expect(at(116, 50)).toEqual([204, 0, 0, 255]);
  });
});

describe("overview shade", () => {
  it("darkens only the played columns", () => {
    const pixels = new Uint8ClampedArray(8 * 4);
    for (let index = 0; index < pixels.length; index += 4) {
      pixels[index] = 100;
      pixels[index + 1] = 80;
      pixels[index + 2] = 40;
      pixels[index + 3] = 255;
    }
    shadePlayed(pixels, 8, 1, 3);
    expect(pixels[0]).toBe(45);
    expect(pixels[1]).toBe(36);
    expect(pixels[8]).toBe(45);
    expect(pixels[12]).toBe(100);
    expect(pixels[13]).toBe(80);
  });
});

describe("frame budget", () => {
  it("draws a 60-minute track without sampling the whole buffer", () => {
    const rate = 150;
    const count = rate * 60 * 60;
    const detail = new Uint8Array(count * 6);
    const mid = 1800 * rate;
    detail[0] = 255;
    detail[mid * 6] = 255;
    detail[mid * 6 + 1] = 80;
    detail[detail.length - 1] = 255;
    const tiles = new DetailTiles(detail, count, rate);
    const width = 800;
    const height = 96;
    const frame = new Uint8ClampedArray(width * height * 4);
    const markers: WaveMarkers = {
      cues: [{ seconds: 1800, color: "#CC0000" }],
      loops: [{ startSeconds: 1790, endSeconds: 1810, color: "#27AAE1" }],
      beatgrid: [{ positionSeconds: 0, bpm: 120 }],
    };
    const cold = tiles.paint(frame, width, height, 1, 1800, 80, markers);
    expect(cold.pointsRead).toBeGreaterThan(0);
    expect(cold.pointsRead).toBeLessThan(20_000);
    const reads: number[] = [];
    const started = performance.now();
    for (let frameIndex = 0; frameIndex < 20; frameIndex += 1) {
      const painted = tiles.paint(frame, width, height, 1, 1800 + frameIndex * 0.01, 80, markers);
      reads.push(painted.pointsRead);
    }
    const perFrame = (performance.now() - started) / 20;
    expect(reads).toEqual(new Array(20).fill(0));
    expect(perFrame).toBeLessThan(FRAME_BUDGET_MS);
    const x = Math.floor(width / 2);
    const offset = (Math.floor(height / 2) * width + x) * 4;
    expect(frame[offset]).toBe(0xe2);
    expect(frame[offset + 1]).toBe(0x3b);
    expect(frame[offset + 2]).toBe(0x16);
  });
});
