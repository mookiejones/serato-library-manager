import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { HOT_LOOPS_STORAGE_KEY, rekordboxExportUrl, restoreHotLoops, wireDialogs } from "./dialogs";
import { el } from "./dom";
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

describe("Hot loops checkbox storage", () => {
  const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");

  beforeEach(() => {
    installPage();
    localStorage.clear();
    state.mode = "crates";
    state.space = "Serato Library";
    state.activeCrate = "all";
  });

  afterEach(() => {
    if (originalStorage) Object.defineProperty(window, "localStorage", originalStorage);
    localStorage.clear();
  });

  function hotLoops(): HTMLInputElement {
    return el("rekordbox-hot-loops");
  }

  it("stays off when nothing is stored", () => {
    wireDialogs();
    expect(hotLoops().checked).toBe(false);
    expect(localStorage.getItem(HOT_LOOPS_STORAGE_KEY)).toBeNull();
    expect(rekordboxExportUrl(false)).toContain("hot_loops=0");
  });

  it("saves a check and restores it on the next visit", () => {
    wireDialogs();
    const box = hotLoops();
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    expect(localStorage.getItem(HOT_LOOPS_STORAGE_KEY)).toBe("1");

    installPage();
    expect(hotLoops().checked).toBe(false);
    wireDialogs();
    expect(hotLoops().checked).toBe(true);
    expect(rekordboxExportUrl(false)).toContain("hot_loops=1");

    const again = hotLoops();
    again.checked = false;
    again.dispatchEvent(new Event("change"));
    expect(localStorage.getItem(HOT_LOOPS_STORAGE_KEY)).toBe("0");
    installPage();
    wireDialogs();
    expect(hotLoops().checked).toBe(false);
    expect(rekordboxExportUrl(false)).toContain("hot_loops=0");
  });

  it("treats any stored value other than 1 as off", () => {
    localStorage.setItem(HOT_LOOPS_STORAGE_KEY, "true");
    restoreHotLoops();
    expect(hotLoops().checked).toBe(false);
    localStorage.setItem(HOT_LOOPS_STORAGE_KEY, "0");
    restoreHotLoops();
    expect(hotLoops().checked).toBe(false);
  });

  it("leaves the box off when localStorage cannot be opened", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("blocked", "SecurityError");
      },
    });
    expect(() => wireDialogs()).not.toThrow();
    expect(hotLoops().checked).toBe(false);
    const box = hotLoops();
    box.checked = true;
    expect(() => box.dispatchEvent(new Event("change"))).not.toThrow();
    expect(box.checked).toBe(true);
    expect(rekordboxExportUrl(false)).toContain("hot_loops=1");
  });

  it("leaves the box usable when getItem and setItem throw", () => {
    const blocked: Storage = {
      get length() {
        return 0;
      },
      clear() {
        throw new DOMException("blocked", "SecurityError");
      },
      getItem() {
        throw new DOMException("blocked", "SecurityError");
      },
      key() {
        throw new DOMException("blocked", "SecurityError");
      },
      removeItem() {
        throw new DOMException("blocked", "SecurityError");
      },
      setItem() {
        throw new DOMException("blocked", "SecurityError");
      },
    };
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: blocked,
    });
    expect(() => restoreHotLoops()).not.toThrow();
    expect(hotLoops().checked).toBe(false);
    wireDialogs();
    const box = hotLoops();
    box.checked = true;
    expect(() => box.dispatchEvent(new Event("change"))).not.toThrow();
    expect(box.checked).toBe(true);
  });
});
