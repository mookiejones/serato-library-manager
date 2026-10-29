import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadPrivacy, rekordboxExportUrl, saveRekordboxExport, wireDialogs } from "./dialogs";
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

function settingsResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

describe("Rekordbox export settings", () => {
  beforeEach(() => {
    installPage();
    state.mode = "crates";
    state.space = "Serato Library";
    state.activeCrate = "all";
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function hotLoops(): HTMLInputElement {
    return el("rekordbox-hot-loops");
  }

  function memoryCues(): HTMLInputElement {
    return el("rekordbox-memory");
  }

  function keyNotation(): HTMLSelectElement {
    return el("rekordbox-key");
  }

  it("loads the saved bar and leaves the HTML defaults when nothing is stored", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(settingsResponse({
      telemetry_consent: null,
      needs_consent_prompt: false,
      rekordbox: { hot_loops: false, memory_cues: true, key_notation: "asis" },
    }));
    await loadPrivacy();
    expect(hotLoops().checked).toBe(false);
    expect(memoryCues().checked).toBe(true);
    expect(keyNotation().value).toBe("asis");
    expect(rekordboxExportUrl(false)).toContain("hot_loops=0");
    expect(rekordboxExportUrl(false)).toContain("memory=1");
    expect(rekordboxExportUrl(false)).toContain("key=asis");
  });

  it("restores hot loops, memory cues, and the key notation", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(settingsResponse({
      telemetry_consent: false,
      needs_consent_prompt: false,
      rekordbox: { hot_loops: true, memory_cues: false, key_notation: "classical" },
    }));
    await loadPrivacy();
    expect(hotLoops().checked).toBe(true);
    expect(memoryCues().checked).toBe(false);
    expect(keyNotation().value).toBe("classical");
    expect(rekordboxExportUrl(false)).toContain("hot_loops=1");
    expect(rekordboxExportUrl(false)).toContain("memory=0");
    expect(rekordboxExportUrl(false)).toContain("key=classical");
  });

  it("posts the three controls when one of them changes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(settingsResponse({
      needs_consent_prompt: false,
      rekordbox: { hot_loops: false, memory_cues: true, key_notation: "asis" },
    }));
    wireDialogs();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fetchMock.mockClear();
    fetchMock.mockResolvedValue(settingsResponse({
      rekordbox: { hot_loops: true, memory_cues: false, key_notation: "camelot" },
    }));
    hotLoops().checked = true;
    memoryCues().checked = false;
    keyNotation().value = "camelot";
    hotLoops().dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls[0];
    expect(call?.[0]).toBe("/api/settings");
    const init = call?.[1];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      rekordbox: { hot_loops: true, memory_cues: false, key_notation: "camelot" },
    });
  });

  it("keeps the export working when settings cannot be loaded", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockRejectedValue(new Error("offline"));
    await expect(loadPrivacy()).rejects.toThrow(/offline|fetch/i);
    expect(hotLoops().checked).toBe(false);
    expect(memoryCues().checked).toBe(true);
    expect(keyNotation().value).toBe("asis");
    expect(rekordboxExportUrl(false)).toContain("hot_loops=0");
    expect(rekordboxExportUrl(false)).toContain("memory=1");
    expect(rekordboxExportUrl(false)).toContain("key=asis");
    fetchMock.mockResolvedValue(settingsResponse({ error: "nope" }, false));
    await expect(loadPrivacy()).rejects.toThrow(/nope/);
    expect(rekordboxExportUrl(true)).toContain("report=1");
  });

  it("keeps a changed box when the save fails", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(settingsResponse({ error: "nope" }, false));
    hotLoops().checked = true;
    await saveRekordboxExport();
    expect(hotLoops().checked).toBe(true);
    expect(rekordboxExportUrl(false)).toContain("hot_loops=1");
    fetchMock.mockRejectedValue(new Error("offline"));
    memoryCues().checked = false;
    await saveRekordboxExport();
    expect(memoryCues().checked).toBe(false);
    expect(rekordboxExportUrl(false)).toContain("memory=0");
  });
});
