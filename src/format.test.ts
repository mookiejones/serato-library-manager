import { beforeEach, describe, expect, it } from "vitest";
import type { Track } from "./api-types";
import { compare, lengthLabel } from "./format";
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
