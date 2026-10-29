import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VersionPayload } from "./api-types";
import { el } from "./dom";
import { installPage } from "./test-page";
import { loadVersion, versionLabel, wireVersion, VERSION_UNAVAILABLE } from "./version";

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

function versionBody(overrides: Partial<VersionPayload> = {}): VersionPayload {
  return {
    version: "v1.4.2",
    commit: "abc123def456",
    source: "release",
    ...overrides,
  };
}

describe("versionLabel", () => {
  it("shows a release tag without the commit", () => {
    expect(versionLabel(versionBody())).toBe("v1.4.2");
  });

  it("adds v to a numeric development version and a short commit", () => {
    expect(versionLabel(versionBody({
      version: "0.0.0+dev",
      commit: "ABC123DEF456",
      source: "dev",
    }))).toBe("v0.0.0+dev · abc123d");
  });

  it("leaves a commit off when the version text already includes it", () => {
    expect(versionLabel(versionBody({
      version: "v1.1.0-rc2-3-gabcdef1",
      commit: "abcdef123456",
      source: "git",
    }))).toBe("v1.1.0-rc2-3-gabcdef1");
  });
});

describe("version on the page", () => {
  beforeEach(() => {
    installPage();
    wireVersion();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function fetchMock(): ReturnType<typeof vi.mocked<typeof fetch>> {
    return vi.mocked(fetch);
  }

  it("shows the version in the footer and in About", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody()));
    await loadVersion();
    const footer = el("app-version");
    expect(footer.hidden).toBe(false);
    expect(footer.textContent).toBe("App version v1.4.2");
    expect(footer.querySelector(".visually-hidden")?.textContent).toBe("App version ");
    expect(el("about-version").textContent).toBe("v1.4.2");
    expect(el("about-version").textContent).not.toBe(VERSION_UNAVAILABLE);
    expect(fetchMock()).toHaveBeenCalledWith("/api/version");
  });

  it("shows a development version with its short commit", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody({
      version: "v1.1.0-rc2",
      commit: "abc123def456",
      source: "git",
    })));
    await loadVersion();
    expect(el("app-version").hidden).toBe(false);
    expect(el("about-version").textContent).toBe("v1.1.0-rc2 · abc123d");
    expect(el("app-version").textContent).toContain("v1.1.0-rc2 · abc123d");
  });

  it("hides the footer and says Version unavailable when the request fails", async () => {
    const raw = "OperationalError: disk I/O error near master.sqlite";
    fetchMock().mockResolvedValue(jsonResponse({ error: raw }, false));
    await loadVersion();
    expect(el("app-version").hidden).toBe(true);
    expect(el("app-version").textContent).toBe("");
    expect(el("about-version").textContent).toBe(VERSION_UNAVAILABLE);
    expect(document.body.textContent).not.toContain(raw);
    expect(document.body.textContent).not.toContain("OperationalError");
  });

  it("treats a rejected request and a malformed body as unavailable", async () => {
    fetchMock().mockRejectedValue(new Error("Failed to fetch: ECONNREFUSED"));
    await loadVersion();
    expect(el("app-version").hidden).toBe(true);
    expect(el("about-version").textContent).toBe(VERSION_UNAVAILABLE);
    expect(document.body.textContent).not.toContain("ECONNREFUSED");

    fetchMock().mockResolvedValue(jsonResponse({ version: "v1.4.2" }));
    await loadVersion();
    expect(el("app-version").hidden).toBe(true);
    expect(el("about-version").textContent).toBe(VERSION_UNAVAILABLE);
    expect(document.body.textContent).not.toContain("v1.4.2");
  });

  it("copies the version from a keyboard-usable button and says Copied", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody()));
    await loadVersion();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    const button = el("copy-version");
    const status = el("version-copy-status");
    expect(button.tagName).toBe("BUTTON");
    expect(button.type).toBe("button");
    expect(button.disabled).toBe(false);
    expect(status.getAttribute("aria-live")).toBe("polite");
    el("settings-dialog").showModal();
    button.focus();
    expect(document.activeElement).toBe(button);
    button.click();
    await vi.waitFor(() => {
      expect(status.textContent).toBe("Copied");
    });
    expect(writeText).toHaveBeenCalledWith("v1.4.2");
  });

  it("does not copy and does not show a raw error when the version is missing", async () => {
    fetchMock().mockResolvedValue(jsonResponse({ error: "nope" }, false));
    await loadVersion();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    el("copy-version").click();
    await vi.waitFor(() => {
      expect(el("version-copy-status").textContent).toBe(VERSION_UNAVAILABLE);
    });
    expect(writeText).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("nope");
  });

  it("says the copy failed without the clipboard exception", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody({ version: "v9.9.9", source: "release" })));
    await loadVersion();
    const writeText = vi.fn().mockRejectedValue(new Error("NotAllowedError: Document is not focused"));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    el("copy-version").click();
    await vi.waitFor(() => {
      expect(el("version-copy-status").textContent).toBe("Couldn't copy the version.");
    });
    expect(document.body.textContent).not.toContain("NotAllowedError");
  });
});
