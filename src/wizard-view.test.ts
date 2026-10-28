/**
 * The setup screen posts the completion flag only from Done.
 *
 * Cancel and Esc close the dialog. The assertions read the fetch body,
 * so a cancel path that posts wizard_complete true fails.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
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
