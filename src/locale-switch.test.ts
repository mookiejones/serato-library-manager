import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "./api-types";
import { applyLanguage, saveLanguage } from "./dialogs";
import { el } from "./dom";
import { PSEUDO, setLocale, t } from "./i18n";
import { repaintAll, wireLocale } from "./locale-wiring";
import { state } from "./state";
import { installPage } from "./test-page";
import { mountTrackList } from "./virtual-scroll";
import { renderList, renderSessions } from "./views";

const fetchMock = vi.hoisted(() => vi.fn());
vi.stubGlobal("fetch", fetchMock);

function track(id: number, name: string): Track {
  return { id, name, artist: "Artist", file: `${id}.mp3`, bpm: 124.5, key: "8A", length_ms: 200000, file_size: 2048 };
}

function columns(): string[] {
  return [...document.querySelectorAll<HTMLButtonElement>(".columns button")].map((button) => button.textContent ?? "");
}

function reset(): void {
  state.tracks = [track(1, "Alpha"), track(2, "Beta")];
  state.byId = new Map(state.tracks.map((item) => [item.id, item]));
  state.crates = [];
  state.crateTracks = new Map();
  state.activeCrate = "all";
  state.query = "";
  state.crateQuery = "";
  state.mode = "crates";
  state.sort = "name";
  state.sortDir = 1;
  state.selectedId = 1;
  state.historySessions = [];
  state.historyId = null;
  state.entries = [];
  state.writable = false;
}

describe("switching the language", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    history.replaceState(null, "", "/");
    vi.stubGlobal("navigator", { languages: ["en-US"], language: "en-US" });
    fetchMock.mockReset();
    fetchMock.mockImplementation(() => {
      throw new Error("a language change must not fetch");
    });
    installPage();
    mountTrackList();
    reset();
  });

  afterEach(() => {
    document.documentElement.lang = "en";
  });

  it("repaints the shell, list, and static labels without reading the library again", () => {
    wireLocale();
    renderList();
    expect(el("count").textContent).toBe("2 tracks");
    expect(columns()).toEqual(["Title", "Artist", "BPM", "Key", "Time"]);
    expect(document.querySelector('[data-view="crates"]')?.textContent).toBe("Crates");
    expect(el("search").placeholder).toBe("Search tracks");
    expect(el("crate-foot").textContent).toBe("2 · 6m · 4.0 KB");

    setLocale("es");

    expect(el("count").textContent).toBe("2 pistas");
    expect(columns()).toEqual(["Título", "Artista", "BPM", "Tono", "Tiempo"]);
    expect(document.querySelector('[data-view="crates"]')?.textContent).toBe("Cajas");
    expect(el("search").placeholder).toBe("Buscar pistas");
    expect(el("crate-foot").textContent).toBe("2 · 6 min · 4,0 KB");
    expect(document.querySelector("#crate-list .name")?.textContent).toBe("Todas las pistas");
    expect(document.querySelector("#list .row .cell.num")?.textContent).toBe("124,5");
    expect(fetchMock).not.toHaveBeenCalled();

    setLocale("en");
    expect(el("count").textContent).toBe("2 tracks");
    expect(document.querySelector('[data-view="crates"]')?.textContent).toBe("Crates");
  });

  it("repaints the open history entry and the session list", () => {
    wireLocale();
    state.mode = "history";
    state.historyId = 4;
    state.historySessions = [{ id: 4, name: "Friday" }];
    state.entries = [{ id: 9, name: "Alpha", artist: "Artist", file: "a.mp3", deck: "1", played: "Yes", start_time: 100, asset_id: 1 } as Track];
    state.selectedId = 9;
    renderSessions();
    renderList();
    const labels = () => [...document.querySelectorAll<HTMLElement>("#detail .label")].map((node) => node.textContent);
    const view = () => document.querySelector("#detail button")?.textContent;
    // renderList left the detail pane alone because the entry was already selected.
    repaintAll();
    expect(labels()).toEqual(["Played", "Deck", "Started", "File"]);
    expect(view()).toBe("Open in library");
    expect(el("count").textContent).toBe("1 play");

    setLocale("es");
    expect(labels()).toEqual(["Reproducida", "Deck", "Inicio", "Archivo"]);
    expect(view()).toBe("Abrir en la biblioteca");
    expect(el("count").textContent).toBe("1 reproducción");
    expect(document.querySelector("#list .row")?.textContent).toContain("Sí");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("listens only once when wired twice", () => {
    wireLocale();
    wireLocale();
    renderList();
    const spy = vi.spyOn(el("count"), "textContent", "set");
    setLocale("es");
    // One repaint: the static pass, then the list. Two listeners would double it.
    expect(spy).toHaveBeenCalledTimes(2);
    expect(el("count").textContent).toBe("2 pistas");
  });

  it("translates the unknown Serato version on the status line", () => {
    wireLocale();
    state.serato = {
      writable: false,
      message: "Serato version is unknown (build 9.9).",
      code: "serato_version_unknown",
      params: { build: "9.9" },
    };
    renderList();
    setLocale("es");
    expect(el("status").textContent).toContain("compilación 9.9");
    expect(el("status").textContent).not.toContain("Writes and restores");
    setLocale("en");
    expect(el("status").textContent).toContain("build 9.9");
  });

  it("keeps the server's status line after the static pass", () => {
    wireLocale();
    state.serato = { writable: false, message: "Serato is open. Changes are paused." };
    el("status").textContent = state.serato.message ?? "";
    renderList();
    setLocale("es");
    expect(el("status").textContent).toBe("Serato is open. Changes are paused.");
    state.serato = { writable: true, message: "" };
    setLocale("en");
    expect(el("status").textContent).toBe("Library");
  });

  it("translates the status line before Serato answers", () => {
    wireLocale();
    state.serato = null;
    setLocale("es");
    expect(el("status").textContent).toBe("Comprobando Serato");
  });

  it("starts in the language the URL asks for", () => {
    history.replaceState(null, "", "/?locale=es");
    wireLocale();
    history.replaceState(null, "", "/");
    expect(document.documentElement.lang).toBe("es");
    expect(document.querySelector('[data-view="history"]')?.textContent).toBe("Historial");
  });

  it("follows the OS language when nothing is saved", () => {
    vi.stubGlobal("navigator", { languages: ["es-CO"], language: "es-CO" });
    wireLocale();
    expect(document.documentElement.lang).toBe("es");
  });
});

describe("the Settings language picker", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    vi.stubGlobal("navigator", { languages: ["en-US"], language: "en-US" });
    fetchMock.mockReset();
    installPage();
    mountTrackList();
    reset();
    wireLocale();
  });

  it("applies a saved language from settings and selects it", () => {
    applyLanguage({ language: "es" });
    expect(document.documentElement.lang).toBe("es");
    expect(el("language-select").value).toBe("es");
    expect(document.getElementById("settings-title")?.textContent).toBe("Ajustes");
  });

  it("follows the OS when the saved language is null or unknown", () => {
    vi.stubGlobal("navigator", { languages: ["es-ES"], language: "es-ES" });
    applyLanguage({ language: null });
    expect(el("language-select").value).toBe("");
    expect(document.documentElement.lang).toBe("es");
    setLocale("en");
    applyLanguage({ language: "fr" });
    expect(el("language-select").value).toBe("");
    expect(document.documentElement.lang).toBe("es");
  });

  it("leaves the page alone when settings say nothing about language", () => {
    setLocale("es");
    applyLanguage({ telemetry_consent: true });
    expect(document.documentElement.lang).toBe("es");
  });

  it("keeps the pseudo-locale for layout checks", () => {
    setLocale(PSEUDO);
    applyLanguage({ language: "en" });
    expect(document.documentElement.lang).toBe(PSEUDO);
    expect(el("language-select").value).toBe("en");
  });

  it("switches at once and saves the choice", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ language: "es" }), { status: 200 }));
    el("language-select").value = "es";
    const pending = saveLanguage();
    expect(document.documentElement.lang).toBe("es");
    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/settings");
    expect(JSON.parse(String(init.body))).toEqual({ language: "es" });
    expect(el("language-status").textContent).toBe("");
  });

  it("saves null for the system choice", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ language: null }), { status: 200 }));
    setLocale("es");
    el("language-select").value = "";
    await saveLanguage();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ language: null });
    expect(document.documentElement.lang).toBe("en");
  });

  it("keeps the new language and says so when the save fails", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ error: "x" }), { status: 500 }));
    el("language-select").value = "es";
    await saveLanguage();
    expect(document.documentElement.lang).toBe("es");
    expect(el("language-status").textContent).toBe(t("settings.languageNotSaved"));
    expect(el("language-status").textContent).toContain("No se pudo");
  });
});
