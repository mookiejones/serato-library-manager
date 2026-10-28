import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import { state } from "./state";
import { installPage } from "./test-page";

let lengthLabel: (ms: number | string | null | undefined) => string;
let compare: (a: Track, b: Track) => number;
let rekordboxExportUrl: (report: boolean) => string;

beforeAll(async () => {
  installPage();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "offline" }), {
    status: 500,
    headers: { "Content-Type": "application/json" },
  })));
  const app = await import("./app");
  lengthLabel = app.lengthLabel;
  compare = app.compare;
  rekordboxExportUrl = app.rekordboxExportUrl;
});

describe("lengthLabel", () => {
  it("formats milliseconds and leaves empty input blank", () => {
    expect(lengthLabel(125000)).toBe("2:05");
    expect(lengthLabel(0)).toBe("0:00");
    expect(lengthLabel(null)).toBe("");
    expect(lengthLabel("")).toBe("");
  });
});

describe("compare", () => {
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

describe("rekordboxExportUrl", () => {
  it("builds the report and download URLs from the current space and crate", () => {
    state.mode = "crates";
    state.space = "Serato Library";
    state.activeCrate = "all";
    const memory = document.getElementById("rekordbox-memory") as HTMLInputElement;
    const key = document.getElementById("rekordbox-key") as HTMLSelectElement;
    memory.checked = true;
    key.value = "camelot";
    expect(rekordboxExportUrl(false)).toBe(
      "/api/export.rekordbox.xml?space=Serato%20Library&crate=all&memory=1&key=camelot",
    );
    expect(rekordboxExportUrl(true)).toBe(
      "/api/export.rekordbox.xml?space=Serato%20Library&crate=all&memory=1&key=camelot&report=1",
    );
    state.mode = "history";
    state.activeCrate = 4;
    memory.checked = false;
    expect(rekordboxExportUrl(false)).toContain("crate=all");
    expect(rekordboxExportUrl(false)).toContain("memory=0");
  });
});
