/**
 * The setup screen posts the completion flag only from Done.
 *
 * Cancel and Esc close the dialog. The assertions read the fetch body,
 * so a cancel path that posts wizard_complete true fails.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setLocale } from "./i18n";
import { installPage } from "./test-page";
import { open } from "./wizard-view";

interface FetchCall {
  url: string;
  method: string;
  body: string | null;
}

const calls: FetchCall[] = [];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function wizardCompletePosts(): FetchCall[] {
  return calls.filter((call) => {
    if (call.method !== "POST" || call.body === null) return false;
    let parsed: unknown;
    try {
      parsed = JSON.parse(call.body);
    } catch {
      return false;
    }
    return isRecord(parsed) && parsed.wizard_complete === true;
  });
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function fakeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const method = (init?.method ?? "GET").toUpperCase();
  const raw = init?.body;
  const body = typeof raw === "string" ? raw : null;
  calls.push({ url, method, body });
  if (url.startsWith("/api/settings") && method === "GET") {
    return jsonResponse({
      telemetry_consent: false,
      needs_consent_prompt: false,
      wizard_complete: false,
      telemetry_configured: false,
      app_version: "1.1.0",
    });
  }
  if (url.startsWith("/api/setup") && method === "GET") {
    return jsonResponse({
      found: true,
      summary: "Found your Serato library on Macintosh HD, 2 tracks.",
      next: "",
      serato_running: false,
      status_message: "Serato is quit. Edits save to the library.",
      status_writable: true,
    });
  }
  if (url.startsWith("/api/snapshots") && method === "POST") {
    return jsonResponse({ ok: true });
  }
  if (url.startsWith("/api/settings") && method === "POST") {
    return jsonResponse({
      telemetry_consent: false,
      needs_consent_prompt: false,
      wizard_complete: true,
      telemetry_configured: false,
      app_version: "1.1.0",
    });
  }
  return jsonResponse({ error: "Not found." }, 404);
}

function wizardDialog(): HTMLDialogElement {
  const node = document.getElementById("wizard");
  if (!(node instanceof HTMLDialogElement)) throw new Error("Missing wizard");
  return node;
}

function button(id: string): HTMLButtonElement {
  const node = document.getElementById(id);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`Missing ${id}`);
  return node;
}

async function openWizard(): Promise<void> {
  open({ returnFocus: document.getElementById("search") });
  await vi.waitFor(() => {
    expect(wizardDialog().open).toBe(true);
    expect(document.getElementById("wizard-title")?.textContent).toBe("See your Serato library");
  });
}

async function reachDone(): Promise<void> {
  await openWizard();
  button("wizard-primary").click();
  await vi.waitFor(() => {
    expect(document.getElementById("wizard-title")?.textContent).toBe("Find your library");
  });
  button("wizard-primary").click();
  await vi.waitFor(() => {
    expect(button("wizard-primary").textContent).toBe("Take a safety snapshot");
  });
  button("wizard-primary").click();
  await vi.waitFor(() => {
    expect(button("wizard-primary").textContent).toBe("Continue");
  });
  button("wizard-primary").click();
  await vi.waitFor(() => {
    expect(button("wizard-primary").textContent).toBe("Open my library");
    expect(wizardDialog().open).toBe(true);
  });
}

describe("setup completion is posted only from Done", () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.stubGlobal("fetch", fakeFetch);
    installPage();
  });

  afterEach(() => {
    calls.length = 0;
  });

  afterAll(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("does not post wizard_complete when Cancel is used", async () => {
    await reachDone();
    calls.length = 0;
    button("wizard-cancel").click();
    await vi.waitFor(() => {
      expect(wizardDialog().open).toBe(false);
    });
    expect(wizardCompletePosts()).toEqual([]);
  });

  it("does not post wizard_complete when Esc cancels the dialog", async () => {
    await reachDone();
    calls.length = 0;
    wizardDialog().dispatchEvent(new Event("cancel", { cancelable: true }));
    await vi.waitFor(() => {
      expect(wizardDialog().open).toBe(false);
    });
    expect(wizardCompletePosts()).toEqual([]);
  });

  it("posts wizard_complete true when Open my library is used", async () => {
    await reachDone();
    calls.length = 0;
    button("wizard-primary").click();
    await vi.waitFor(() => {
      expect(wizardCompletePosts()).toHaveLength(1);
      expect(wizardDialog().open).toBe(false);
    });
    const call = wizardCompletePosts()[0];
    expect(call?.url).toContain("/api/settings");
    expect(call?.method).toBe("POST");
    expect(call?.body).toBe(JSON.stringify({ wizard_complete: true }));
  });
});

describe("setup follows the page language", () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.stubGlobal("fetch", fakeFetch);
    // The wizard wires its buttons once, so keep the page it wired.
    if (!document.getElementById("wizard")) installPage();
  });

  afterEach(() => {
    calls.length = 0;
    if (wizardDialog().open) button("wizard-cancel").click();
    setLocale("en");
  });

  afterAll(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("repaints the open step when the language changes", async () => {
    await openWizard();
    expect(document.getElementById("wizard-step-label")?.textContent).toBe("Step 1 of 4");
    setLocale("es");
    expect(document.getElementById("wizard-title")?.textContent).toBe("Mira tu biblioteca de Serato");
    expect(document.getElementById("wizard-step-label")?.textContent).toBe("Paso 1 de 4");
    expect(button("wizard-primary").textContent).toBe("Empezar");
    expect(document.getElementById("wizard-body")?.textContent).toContain("Esta app muestra");
    button("wizard-primary").click();
    await vi.waitFor(() => {
      expect(document.getElementById("wizard-title")?.textContent).toBe("Encuentra tu biblioteca");
    });
    // The server summary is data and stays as sent.
    expect(document.getElementById("wizard-body")?.textContent).toBe("Found your Serato library on Macintosh HD, 2 tracks.");
    expect(button("wizard-primary").textContent).toBe("Usar esta biblioteca");
  });

  it("shows a translated server error by its code", async () => {
    await openWizard();
    const original = fakeFetch;
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : String(input);
      if (url.startsWith("/api/settings") && init?.method === "POST") {
        return jsonResponse({ error: "Setup could not be saved.", code: "setup_not_saved" }, 500);
      }
      return original(input, init);
    });
    setLocale("es");
    await reachDoneFromWelcome();
    button("wizard-primary").click();
    await vi.waitFor(() => {
      expect(document.getElementById("wizard-status")?.textContent).toBe("No se pudo guardar la configuración.");
    });
    vi.stubGlobal("fetch", fakeFetch);
  });
});

async function reachDoneFromWelcome(): Promise<void> {
  button("wizard-primary").click();
  await vi.waitFor(() => expect(button("wizard-primary").textContent).toBe("Usar esta biblioteca"));
  button("wizard-primary").click();
  await vi.waitFor(() => expect(button("wizard-primary").textContent).toBe("Tomar una instantánea de seguridad"));
  button("wizard-primary").click();
  await vi.waitFor(() => expect(button("wizard-primary").textContent).toBe("Continuar"));
  button("wizard-primary").click();
  await vi.waitFor(() => expect(button("wizard-primary").textContent).toBe("Abrir mi biblioteca"));
}
