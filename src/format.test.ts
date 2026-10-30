import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Track } from "./api-types";
import { clockLabel, compare, durationLabel, lengthLabel, sizeLabel } from "./format";
import { setLocale } from "./i18n";
import { state } from "./state";

describe("lengthLabel", () => {
  it("formats milliseconds and leaves empty input blank", () => {
    expect(lengthLabel(125000)).toBe("2:05");
    expect(lengthLabel(0)).toBe("0:00");
    expect(lengthLabel(null)).toBe("");
    expect(lengthLabel("")).toBe("");
  });
});

describe("compare", () => {
  beforeEach(() => {
    state.sort = "name";
    state.sortDir = 1;
  });

  it("sorts titles with numbers in numeric order and puts an empty BPM last", () => {
    state.sort = "name";
    state.sortDir = 1;
    const early = { id: 2, name: "Track 2" } as Track;
    const later = { id: 10, name: "Track 10" } as Track;
    expect(compare(early, later)).toBeLessThan(0);
    expect(compare(later, early)).toBeGreaterThan(0);

    state.sort = "bpm";
    state.sortDir = 1;
    const empty = { id: 1, bpm: null } as Track;
    const timed = { id: 3, bpm: 120 } as Track;
    expect(compare(empty, timed)).toBe(1);
    expect(compare({ id: 4, bpm: 128 } as Track, { id: 5, bpm: 100 } as Track)).toBeGreaterThan(0);
  });
});

describe("labels in the active language", () => {
  afterEach(() => {
    setLocale("en");
  });

  it("formats durations, sizes, and dates for English", () => {
    expect(durationLabel(62 * 60 * 1000)).toBe("1h 2m");
    expect(durationLabel(12 * 60 * 1000)).toBe("12m");
    expect(sizeLabel(1)).toBe("1 byte");
    expect(sizeLabel(512)).toBe("512 bytes");
    expect(sizeLabel(1536)).toBe("1.5 KB");
    expect(sizeLabel(5 * 1024 * 1024 * 1024 * 1024)).toBe("5,120.0 GB");
    expect(clockLabel(Date.UTC(2026, 0, 2, 12) / 1000)).toMatch(/^Jan 2,/);
  });

  it("formats durations, sizes, and dates for Spanish", () => {
    setLocale("es");
    expect(durationLabel(62 * 60 * 1000)).toBe("1 h 2 min");
    expect(durationLabel(12 * 60 * 1000)).toBe("12 min");
    expect(sizeLabel(1)).toBe("1 byte");
    expect(sizeLabel(512)).toBe("512 bytes");
    expect(sizeLabel(1536)).toBe("1,5 KB");
    expect(sizeLabel(5 * 1024 * 1024 * 1024 * 1024)).toBe("5120,0 GB");
    expect(clockLabel(Date.UTC(2026, 0, 2, 12) / 1000)).toMatch(/^2 ene/);
  });

  it("sorts titles with the active locale", () => {
    state.sort = "name";
    state.sortDir = 1;
    setLocale("es");
    const n = { id: 1, name: "nube" } as Track;
    const enye = { id: 2, name: "ñu" } as Track;
    const o = { id: 3, name: "oso" } as Track;
    expect([o, enye, n].sort(compare).map((item) => item.name)).toEqual(["nube", "ñu", "oso"]);
  });
});
