/**
 * An older Serato library (database V2, no master.sqlite) is described in
 * plain words on the library step, not as "not found", and setup does not
 * move on to the safety snapshot, which needs the newer library file.
 */

import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { installPage } from "./test-page";
import { open } from "./wizard-view";

const LEGACY_SUMMARY = "Found an older Serato library on Macintosh HD, 5 tracks.";
const LEGACY_NEXT =
  "This library was made by an older Serato DJ. You can look at your tracks, missing files, and duplicates, but this app will not change anything in it yet.";

const posts: string[] = [];

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function fakeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const method = (init?.method ?? "GET").toUpperCase();
  if (method === "POST") posts.push(url);
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
      found: false,
      legacy: true,
      read_only: true,
      summary: LEGACY_SUMMARY,
      next: LEGACY_NEXT,
      serato_running: false,
      status_message: "This library was made by an older Serato DJ. This app can show it but cannot change it yet.",
      status_writable: false,
    });
  }
  return jsonResponse({ error: "Not found." }, 404);
}

function text(id: string): string {
  return document.getElementById(id)?.textContent ?? "";
}

function button(id: string): HTMLButtonElement {
  const node = document.getElementById(id);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`Missing ${id}`);
  return node;
}

describe("setup on an older database V2 library", () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.stubGlobal("fetch", fakeFetch);
    installPage();
  });

  afterAll(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("says an older library was found instead of not found, and stays read-only", async () => {
    open({ returnFocus: document.getElementById("search"), force: true });
    await vi.waitFor(() => {
      expect(text("wizard-title")).toBe("See your Serato library");
    });
    button("wizard-primary").click();
    await vi.waitFor(() => {
      expect(text("wizard-title")).toBe("Find your library");
    });
    expect(text("wizard-body")).toBe(LEGACY_SUMMARY);
    expect(text("wizard-body")).not.toContain("No Serato library was found");
    const hint = document.getElementById("wizard-next");
    expect(hint?.hidden).toBe(false);
    expect(hint?.textContent).toBe(LEGACY_NEXT);
    expect(button("wizard-primary").textContent).not.toBe("Take a safety snapshot");
    expect(posts.filter((url) => url.startsWith("/api/snapshots"))).toEqual([]);
  });
});
