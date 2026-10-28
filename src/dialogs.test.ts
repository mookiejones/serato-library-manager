import { beforeEach, describe, expect, it } from "vitest";
import { rekordboxExportUrl } from "./dialogs";
import { state } from "./state";
import { installPage } from "./test-page";

describe("rekordboxExportUrl", () => {
  beforeEach(() => {
    installPage();
    state.mode = "crates";
    state.space = "Serato Library";
    state.activeCrate = "all";
  });

  it("builds the report and download URLs from the current space and crate", () => {
    const memory = document.getElementById("rekordbox-memory") as HTMLInputElement;
    const hotLoops = document.getElementById("rekordbox-hot-loops") as HTMLInputElement;
    const key = document.getElementById("rekordbox-key") as HTMLSelectElement;
    memory.checked = true;
    hotLoops.checked = false;
    key.value = "camelot";
    expect(rekordboxExportUrl(false)).toBe(
      "/api/export.rekordbox.xml?space=Serato%20Library&crate=all&memory=1&hot_loops=0&key=camelot",
    );
    expect(rekordboxExportUrl(true)).toBe(
      "/api/export.rekordbox.xml?space=Serato%20Library&crate=all&memory=1&hot_loops=0&key=camelot&report=1",
    );
    hotLoops.checked = true;
    expect(rekordboxExportUrl(false)).toContain("hot_loops=1");
    state.mode = "history";
    state.activeCrate = 4;
    memory.checked = false;
    hotLoops.checked = false;
    expect(rekordboxExportUrl(false)).toContain("crate=all");
    expect(rekordboxExportUrl(false)).toContain("memory=0");
    expect(rekordboxExportUrl(false)).toContain("hot_loops=0");
  });
});
