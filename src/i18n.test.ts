import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../locales/en.json";
import es from "../locales/es.json";
import {
  applyStatic,
  formatDate,
  formatList,
  formatNumber,
  getLocale,
  hasKey,
  initialLocale,
  isLanguage,
  LANGUAGES,
  LOCALE_EVENT,
  matchLanguage,
  onLocaleChange,
  pseudo,
  PSEUDO,
  resolveLocale,
  serverMessage,
  setLocale,
  t,
  type Message,
} from "./i18n";
import { installPage } from "./test-page";

const CATALOGS: Record<string, Record<string, Message>> = { en, es };

function placeholders(message: Message): string[] {
  const texts = typeof message === "string" ? [message] : Object.values(message);
  const names = new Set<string>();
  for (const text of texts) {
    for (const match of text.matchAll(/\{([a-zA-Z0-9_]+)\}/g)) names.add(match[1]!);
  }
  return [...names].sort();
}

afterEach(() => {
  document.documentElement.lang = "en";
  vi.unstubAllGlobals();
});

describe("locale catalogs", () => {
  it("ship one catalog per language in LANGUAGES", () => {
    expect([...LANGUAGES].sort()).toEqual(Object.keys(CATALOGS).sort());
  });

  for (const [code, catalog] of Object.entries(CATALOGS)) {
    it(`${code} has exactly the English keys`, () => {
      expect(Object.keys(catalog).sort()).toEqual(Object.keys(en).sort());
    });

    it(`${code} keeps the English placeholders and plural shape`, () => {
      for (const [key, source] of Object.entries(en) as Array<[string, Message]>) {
        const message = catalog[key]!;
        expect(typeof message, key).toBe(typeof source);
        expect(placeholders(message), key).toEqual(placeholders(source));
        if (typeof message !== "string") {
          expect(message.other, key).toBeTruthy();
          // A plural message must count something.
          expect(placeholders(message), key).toContain("count");
        }
      }
    });

    it(`${code} has no empty messages`, () => {
      for (const [key, message] of Object.entries(catalog)) {
        const texts = typeof message === "string" ? [message] : Object.values(message);
        for (const text of texts) expect(text.trim(), key).not.toBe("");
      }
    });
  }

  it("translates Spanish rather than copying English for most keys", () => {
    // Brand names and units may match. Everything else should differ.
    const same = Object.keys(en).filter((key) => JSON.stringify(es[key as keyof typeof es]) === JSON.stringify(en[key as keyof typeof en]));
    expect(same.length).toBeLessThan(Object.keys(en).length * 0.1);
  });
});

describe("t", () => {
  it("returns English by default and fills params", () => {
    expect(getLocale()).toBe("en");
    expect(t("files.open", { name: "Crate" })).toBe("Open Crate");
    expect(t("files.open")).toBe("Open {name}");
  });

  it("chooses plural forms with Intl.PluralRules and formats numbers", () => {
    expect(t("count.tracks", { count: 1 })).toBe("1 track");
    expect(t("count.tracks", { count: 0 })).toBe("0 tracks");
    expect(t("count.tracks", { count: 2 })).toBe("2 tracks");
    expect(t("count.tracks", { count: 12345 })).toBe("12,345 tracks");
    expect(t("count.tracks")).toBe("{count} tracks");
  });

  it("switches language for the same key", () => {
    setLocale("es");
    expect(t("count.tracks", { count: 1 })).toBe("1 pista");
    expect(t("count.tracks", { count: 3 })).toBe("3 pistas");
    expect(t("count.tracks", { count: 12345 })).toBe("12.345 pistas");
    expect(t("view.crates")).toBe("Cajas");
  });

  it("does not format a string param", () => {
    expect(t("error.requestStatus", { status: "1234" })).toBe("Request failed (1234)");
  });

  it("wraps every message in the pseudo-locale", () => {
    setLocale(PSEUDO);
    const text = t("files.open", { name: "Crate" });
    expect(text.startsWith("[")).toBe(true);
    expect(text.endsWith("]")).toBe(true);
    expect(text).toContain("Crate");
    expect(text).not.toContain("Open");
  });
});

describe("pseudo", () => {
  it("accents letters, keeps placeholders, and pads by about 30 percent", () => {
    const text = pseudo("Open {name} now");
    expect(text).toMatch(/^\[Øpéñ \{name\} ñöw ~+\]$/);
    const pad = text.match(/~+/)![0].length;
    expect(pad).toBe(Math.ceil("Open  now".length * 0.3));
  });

  it("makes every English message at least 30 percent longer", () => {
    for (const [key, message] of Object.entries(en) as Array<[string, Message]>) {
      const texts = typeof message === "string" ? [message] : Object.values(message);
      for (const text of texts) {
        const bare = text.replace(/\{[a-zA-Z0-9_]+\}/g, "");
        const out = pseudo(text).replace(/\{[a-zA-Z0-9_]+\}/g, "");
        expect(out.length, key).toBeGreaterThanOrEqual(Math.ceil(bare.length * 1.3));
      }
    }
  });
});

describe("language choice", () => {
  it("matches a region tag to its language and falls back to English", () => {
    expect(matchLanguage(["es-MX", "en-US"])).toBe("es");
    expect(matchLanguage(["fr-FR", "ES_es"])).toBe("es");
    expect(matchLanguage(["fr-FR", "de"])).toBe("en");
    expect(matchLanguage([])).toBe("en");
  });

  it("prefers a saved language over the OS", () => {
    expect(resolveLocale("en", ["es-ES"])).toBe("en");
    expect(resolveLocale(null, ["es-ES"])).toBe("es");
    expect(resolveLocale("fr", ["es-ES"])).toBe("es");
    expect(resolveLocale(undefined, ["de"])).toBe("en");
  });

  it("knows only the shipped languages", () => {
    expect(isLanguage("es")).toBe(true);
    expect(isLanguage("en")).toBe(true);
    expect(isLanguage(PSEUDO)).toBe(false);
    expect(isLanguage("fr")).toBe(false);
    expect(isLanguage(null)).toBe(false);
  });

  it("starts from the URL, then the OS", () => {
    vi.stubGlobal("navigator", { languages: ["es-AR"], language: "es-AR" });
    expect(initialLocale()).toBe("es");
    vi.stubGlobal("navigator", { languages: [], language: "fr-FR" });
    expect(initialLocale()).toBe("en");
    vi.stubGlobal("navigator", { languages: [], language: "es-ES" });
    expect(initialLocale()).toBe("es");
    history.replaceState(null, "", "/?locale=qps-ploc");
    expect(initialLocale()).toBe(PSEUDO);
    history.replaceState(null, "", "/?locale=es");
    expect(initialLocale()).toBe("es");
    history.replaceState(null, "", "/");
  });

  it("sets <html lang> and tells listeners once per change", () => {
    const seen: string[] = [];
    const stop = onLocaleChange((locale) => seen.push(locale));
    expect(setLocale("es")).toBe(true);
    expect(setLocale("es")).toBe(false);
    expect(document.documentElement.lang).toBe("es");
    setLocale(PSEUDO);
    expect(document.documentElement.lang).toBe(PSEUDO);
    stop();
    setLocale("en");
    expect(seen).toEqual(["es", PSEUDO]);
  });

  it("shares the locale through the document event", () => {
    const heard = vi.fn();
    document.addEventListener(LOCALE_EVENT, heard);
    setLocale("es");
    document.removeEventListener(LOCALE_EVENT, heard);
    expect(heard).toHaveBeenCalledTimes(1);
  });
});

describe("serverMessage", () => {
  it("translates a known error code", () => {
    setLocale("es");
    expect(serverMessage({ error: "That request is not valid.", code: "invalid_request" }, "x")).toBe("Esa solicitud no es válida.");
  });

  it("fills params for a coded notice and accents it in the pseudo-locale", () => {
    const body = {
      error: "Serato version is unknown (build 9.9).",
      code: "serato_version_unknown",
      params: { build: "9.9" },
    };
    setLocale("es");
    const spanish = serverMessage(body, "x");
    expect(spanish).toContain("compilación 9.9");
    expect(spanish).not.toContain("Writes and restores");
    setLocale(PSEUDO);
    const pseudoText = serverMessage(body, "x");
    expect(pseudoText.startsWith("[")).toBe(true);
    expect(pseudoText).toContain("9.9");
    expect(pseudoText).not.toContain("Writes and restores");
    setLocale("en");
  });

  it("translates the Rekordbox cue options", () => {
    expect(es["rekordbox.hotLoops"]).toBe("Bucles de hot cue");
    expect(es["rekordbox.memoryCues"]).toBe("Cues de memoria");
    expect(es["rekordbox.hotLoops"]).not.toBe(en["rekordbox.hotLoops"]);
    expect(es["rekordbox.memoryCues"]).not.toBe(en["rekordbox.memoryCues"]);
  });

  it("keeps the server text for an unknown code or no code", () => {
    setLocale("es");
    expect(serverMessage({ error: "Odd failure", code: "not_a_code" }, "x")).toBe("Odd failure");
    expect(serverMessage({ error: "Odd failure" }, "x")).toBe("Odd failure");
    expect(serverMessage({}, "fallback")).toBe("fallback");
    expect(serverMessage(null, "fallback")).toBe("fallback");
  });

  it("checks keys by name", () => {
    expect(hasKey("error.invalid_request")).toBe(true);
    expect(hasKey("error.nope")).toBe(false);
    expect(hasKey("toString")).toBe(false);
  });
});

describe("formatting", () => {
  it("formats numbers, dates, and lists for the active locale", () => {
    const date = new Date(2026, 0, 2, 15, 4);
    expect(formatNumber(1234.5)).toBe("1,234.5");
    expect(formatList(["a", "b", "c"])).toBe("a, b, and c");
    const english = formatDate(date, { month: "long" });
    setLocale("es");
    expect(formatNumber(1234.5)).toBe("1234,5");
    expect(formatNumber(12345.5)).toBe("12.345,5");
    expect(formatList(["a", "b", "c"])).toBe("a, b y c");
    expect(english).toBe("January");
    expect(formatDate(date, { month: "long" })).toBe("enero");
  });
});

describe("applyStatic", () => {
  beforeEach(() => {
    installPage();
  });

  it("translates text and attributes, and leaves unknown keys alone", () => {
    const host = document.createElement("div");
    host.innerHTML = `
      <p data-i18n="view.crates">Crates</p>
      <p data-i18n="no.such.key">Keep me</p>
      <input data-i18n-attr="placeholder:crates.find; aria-label:search.tracks" placeholder="Find a crate">`;
    setLocale("es");
    expect(applyStatic(host)).toBe(2);
    expect(host.querySelector("p")!.textContent).toBe("Cajas");
    expect(host.querySelectorAll("p")[1]!.textContent).toBe("Keep me");
    const input = host.querySelector("input")!;
    expect(input.placeholder).toBe("Buscar una caja");
    expect(input.getAttribute("aria-label")).toBe("Buscar pistas");
  });

  it("keeps index.html in English so the page reads before any script", () => {
    for (const node of document.querySelectorAll<HTMLElement>("[data-i18n]")) {
      const key = node.dataset.i18n ?? "";
      expect(hasKey(key), key).toBe(true);
      expect(node.textContent, key).toBe(en[key as keyof typeof en]);
    }
  });

  it("leaves no visible markup untranslated in the pseudo-locale", () => {
    setLocale(PSEUDO);
    applyStatic(document);
    // Set at runtime, brand names, or the language names in their own language.
    const runtime = new Set(["wizard-primary"]);
    const brands = new Set(["Rekordbox", "English", "Español"]);
    const leftover: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = (node.textContent ?? "").trim();
      if (!/[A-Za-z]/.test(text) || brands.has(text)) continue;
      const parent = node.parentElement!;
      if (parent.closest("svg, .columns") || runtime.has(parent.id)) continue;
      if (!text.startsWith("[")) leftover.push(text);
    }
    expect(leftover).toEqual([]);
    for (const node of document.querySelectorAll<HTMLElement>("[placeholder], [aria-label], [title]")) {
      for (const attr of ["placeholder", "aria-label", "title"]) {
        const value = node.getAttribute(attr);
        if (value && /[A-Za-z]/.test(value)) expect(value.startsWith("["), `${node.id || node.tagName} ${attr}`).toBe(true);
      }
    }
  });

  it("offers every shipped language in Settings", () => {
    const options = [...document.querySelectorAll<HTMLOptionElement>("#language-select option")].map((option) => option.value);
    expect(options).toEqual(["", ...LANGUAGES]);
  });
});
