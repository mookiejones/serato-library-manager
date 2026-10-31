/**
 * Page language: message lookup, plurals, and the active locale.
 *
 * Messages live in locales/<code>.json at the repository root. English is
 * the source; every other catalog must have every English key, which
 * `satisfies Catalog` checks at compile time, so a missing key fails tsc.
 * A message is a string or a set of plural forms chosen with
 * Intl.PluralRules. `{name}` in a message is replaced from the params;
 * a number param is formatted for the active locale.
 *
 * The page bundle and the wizard bundle each include this module. They
 * share the active locale through `<html lang>` and a `serato-locale`
 * event on the document, so a change in one updates the other.
 *
 * No request is made here, and nothing is kept in browser storage. The
 * saved choice lives in settings.json and is read and written by the
 * callers through GET and POST /api/settings.
 */

import en from "../locales/en.json";
import es from "../locales/es.json";

export type MessageKey = keyof typeof en;

/** Plural forms keyed by Intl.PluralRules category. `other` is required. */
export interface PluralMessage {
  zero?: string;
  one?: string;
  two?: string;
  few?: string;
  many?: string;
  other: string;
}

export type Message = string | PluralMessage;
export type Catalog = { readonly [K in MessageKey]: Message };
export type Params = Readonly<Record<string, string | number>>;

/** Languages a person can choose. Keep in sync with LANGUAGES in app_config.py. */
export const LANGUAGES = ["en", "es"] as const;
export type Language = (typeof LANGUAGES)[number];

/** Pseudo-locale for layout checks. Not offered in Settings. */
export const PSEUDO = "qps-ploc";
export type Locale = Language | typeof PSEUDO;

/** The name of each language in that language, for the picker. */
export const LANGUAGE_NAMES: Readonly<Record<Language, string>> = {
  en: "English",
  es: "Español",
};

const CATALOGS: Readonly<Record<Language, Catalog>> = {
  en: en satisfies Catalog,
  es: es satisfies Catalog,
};

export const LOCALE_EVENT = "serato-locale";

/**
 * Return whether a value is a language code the page ships.
 *
 * @param value Candidate code.
 * @returns True for a code in LANGUAGES.
 */
export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (LANGUAGES as readonly string[]).includes(value);
}

/**
 * Pick a shipped language from browser language tags.
 *
 * "es-MX" matches "es". The first tag that matches wins. English is the
 * fallback when none match.
 *
 * @param tags Language tags, usually navigator.languages.
 * @returns A code from LANGUAGES.
 */
export function matchLanguage(tags: readonly string[]): Language {
  for (const tag of tags) {
    const base = tag.toLowerCase().split(/[-_]/)[0];
    if (isLanguage(base)) return base;
  }
  return "en";
}

/**
 * Resolve the locale to use.
 *
 * A saved choice wins. With none, the OS language is used.
 *
 * @param saved The saved language, or null to follow the OS.
 * @param tags Browser language tags.
 * @returns The locale.
 */
export function resolveLocale(saved: unknown, tags: readonly string[]): Language {
  return isLanguage(saved) ? saved : matchLanguage(tags);
}

function browserTags(): string[] {
  if (typeof navigator === "undefined") return [];
  if (Array.isArray(navigator.languages) && navigator.languages.length) return [...navigator.languages];
  return navigator.language ? [navigator.language] : [];
}

/**
 * Return the active locale.
 *
 * Read from `<html lang>` so both bundles agree.
 *
 * @returns A shipped language or the pseudo-locale.
 */
export function getLocale(): Locale {
  const lang = typeof document === "undefined" ? "" : document.documentElement.lang;
  if (lang === PSEUDO) return PSEUDO;
  return isLanguage(lang) ? lang : "en";
}

/**
 * Set the active locale and tell every listener.
 *
 * Writes `<html lang>` and dispatches the locale event on the document.
 * Setting the same locale again does nothing.
 *
 * @param locale The new locale.
 * @returns True when the locale changed.
 */
export function setLocale(locale: Locale): boolean {
  const root = document.documentElement;
  if (root.lang === locale) return false;
  root.lang = locale;
  document.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
  return true;
}

/**
 * Pick the first locale before settings load.
 *
 * `?locale=qps-ploc` turns on the pseudo-locale, and `?locale=es` picks a
 * language. Otherwise the OS language is used until the saved choice
 * arrives with GET /api/settings.
 *
 * @returns The starting locale.
 */
export function initialLocale(): Locale {
  try {
    const wanted = new URLSearchParams(location.search).get("locale");
    if (wanted === PSEUDO) return PSEUDO;
    if (isLanguage(wanted)) return wanted;
  } catch {
    // No location in this environment.
  }
  return matchLanguage(browserTags());
}

/**
 * Call `listener` after every locale change.
 *
 * @param listener Receives the new locale.
 * @returns A function that removes the listener.
 */
export function onLocaleChange(listener: (locale: Locale) => void): () => void {
  const handler = (): void => listener(getLocale());
  document.addEventListener(LOCALE_EVENT, handler);
  return () => document.removeEventListener(LOCALE_EVENT, handler);
}

const ACCENTS: Readonly<Record<string, string>> = {
  a: "à", e: "é", i: "ï", o: "ö", u: "ü", c: "ç", n: "ñ", y: "ý",
  A: "Å", E: "É", I: "Î", O: "Ø", U: "Û", C: "Ç", N: "Ñ", Y: "Ý",
};

/**
 * Turn English text into pseudo-locale text.
 *
 * Letters get accents, the text is padded by about 30 percent, and it is
 * wrapped in brackets, so a string that skipped t() stands out and a
 * layout that cannot take longer text breaks visibly. `{name}`
 * placeholders are kept.
 *
 * @param text English message text.
 * @returns The pseudo text.
 */
export function pseudo(text: string): string {
  const parts = text.split(/(\{[a-zA-Z0-9_]+\})/);
  const body = parts
    .map((part) => (part.startsWith("{") ? part : part.replace(/[a-zA-Z]/g, (ch) => ACCENTS[ch] ?? ch)))
    .join("");
  const letters = text.replace(/\{[a-zA-Z0-9_]+\}/g, "").length;
  const pad = "~".repeat(Math.max(1, Math.ceil(letters * 0.3)));
  return `[${body} ${pad}]`;
}

function catalogFor(locale: Locale): Catalog {
  return locale === PSEUDO ? CATALOGS.en : CATALOGS[locale];
}

function pick(message: Message, count: number | undefined, locale: Locale): string {
  if (typeof message === "string") return message;
  if (count === undefined) return message.other;
  const rules = new Intl.PluralRules(locale === PSEUDO ? "en" : locale);
  const exact = count === 0 ? message.zero : undefined;
  return exact ?? message[rules.select(count)] ?? message.other;
}

function fill(text: string, params: Params | undefined, locale: Locale): string {
  if (!params) return text;
  const tag = locale === PSEUDO ? "en" : locale;
  return text.replace(/\{([a-zA-Z0-9_]+)\}/g, (whole, name: string) => {
    const value = params[name];
    if (value === undefined) return whole;
    return typeof value === "number" ? new Intl.NumberFormat(tag).format(value) : value;
  });
}

/**
 * Look up a message in the active locale.
 *
 * A plural message uses `params.count`. A `{name}` placeholder with no
 * param is left as written. A key missing from a non-English catalog at
 * runtime falls back to English.
 *
 * @param key Message key from locales/en.json.
 * @param params Placeholder values.
 * @returns The message text.
 */
export function t(key: MessageKey, params?: Params): string {
  const locale = getLocale();
  const message = catalogFor(locale)[key] ?? CATALOGS.en[key];
  const count = typeof params?.count === "number" ? params.count : undefined;
  const template = pick(message, count, locale);
  // Pseudo text changes the message only, so names and paths stay readable.
  return fill(locale === PSEUDO ? pseudo(template) : template, params, locale);
}

/**
 * Return whether a string is a message key.
 *
 * Used for keys built at runtime, such as `error.<code>` from the server.
 *
 * @param key Candidate key.
 * @returns True when English has that key.
 */
export function hasKey(key: string): key is MessageKey {
  return Object.prototype.hasOwnProperty.call(CATALOGS.en, key);
}

/**
 * Keep string and number placeholders from a server `params` object.
 *
 * Anything else is dropped, so a bad payload cannot be interpolated.
 *
 * @param value The server's params object, if any.
 * @returns Placeholder values, or undefined when there are none.
 */
export function messageParams(value: unknown): Params | undefined {
  if (!value || typeof value !== "object") return undefined;
  const params: Record<string, string | number> = {};
  for (const [name, item] of Object.entries(value)) {
    if (typeof item === "string" || (typeof item === "number" && Number.isFinite(item))) params[name] = item;
  }
  return Object.keys(params).length ? params : undefined;
}

/**
 * Show a coded server sentence in the active language.
 *
 * A known `error.<code>` is translated, and `params` fill its
 * placeholders. An unknown code returns `text` unchanged.
 *
 * @param text English sentence from the server.
 * @param code Stable code, if the server sent one.
 * @param params Placeholder values for that code.
 * @returns The text to show.
 */
export function codedText(text: string, code?: string | null, params?: Params | null): string {
  if (typeof code === "string") {
    const key = `error.${code}`;
    if (hasKey(key)) return t(key, params ?? undefined);
  }
  return text;
}

/**
 * Show a server error in the active language.
 *
 * The server sends the English sentence in `error` and, for known ones,
 * a stable `code`. A parameterized notice also sends `params`. A known
 * code is translated. Otherwise the English text is shown, then the fallback.
 *
 * @param body The server error object, if any.
 * @param fallback Text when the body has neither.
 * @returns The text to show.
 */
export function serverMessage(
  body: { error?: string | undefined; code?: string | undefined; params?: Params | undefined } | null | undefined,
  fallback: string,
): string {
  if (typeof body?.code === "string") return codedText(body.error || fallback, body.code, body.params);
  return body?.error || fallback;
}

/**
 * Translate the static markup under `root`.
 *
 * `data-i18n="key"` sets the text. `data-i18n-attr="attr:key;attr:key"`
 * sets attributes such as placeholder, title, and aria-label. index.html
 * keeps its English text, so the page still reads before this runs.
 *
 * @param root Element or document to translate.
 * @returns The number of elements updated.
 */
export function applyStatic(root: ParentNode): number {
  let count = 0;
  for (const node of root.querySelectorAll<HTMLElement>("[data-i18n]")) {
    const key = node.dataset.i18n ?? "";
    if (!hasKey(key)) continue;
    node.textContent = t(key);
    count += 1;
  }
  for (const node of root.querySelectorAll<HTMLElement>("[data-i18n-attr]")) {
    for (const pair of (node.dataset.i18nAttr ?? "").split(";")) {
      const [attr, key] = pair.split(":").map((part) => part.trim());
      if (!attr || !key || !hasKey(key)) continue;
      node.setAttribute(attr, t(key));
    }
    count += 1;
  }
  return count;
}

/** Format a number for the active locale. */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  const locale = getLocale();
  return new Intl.NumberFormat(locale === PSEUDO ? "en" : locale, options).format(value);
}

/** Format a date for the active locale. */
export function formatDate(date: Date, options?: Intl.DateTimeFormatOptions): string {
  const locale = getLocale();
  return new Intl.DateTimeFormat(locale === PSEUDO ? "en" : locale, options).format(date);
}

/** Join items as a list ("a, b, and c") for the active locale. */
export function formatList(items: readonly string[]): string {
  const locale = getLocale();
  return new Intl.ListFormat(locale === PSEUDO ? "en" : locale, { style: "long", type: "conjunction" }).format(items);
}
