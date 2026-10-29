import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VersionPayload } from "./api-types";
import { el } from "./dom";
import { installPage } from "./test-page";
import { getVersion } from "./api";
import { copyVersion, loadVersion, versionLabel, wireVersion, VERSION_UNAVAILABLE } from "./version";

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

  it("trims a padded version and adds v only to a leading numeric triple", () => {
    expect(versionLabel(versionBody({ version: "  v1.4.2  " }))).toBe("v1.4.2");
    expect(versionLabel(versionBody({ version: "  1.4.2  " }))).toBe("v1.4.2");
    expect(versionLabel(versionBody({ version: "  10.4.2  ", source: "dev", commit: null }))).toBe("v10.4.2");
    expect(versionLabel(versionBody({ version: "  1.10.2  ", source: "dev", commit: null }))).toBe("v1.10.2");
    expect(versionLabel(versionBody({ version: "1.2.10", source: "dev", commit: null }))).toBe("v1.2.10");
    expect(versionLabel(versionBody({ version: "rev1.2.3", source: "git", commit: null }))).toBe("rev1.2.3");
    expect(versionLabel(versionBody({ version: "abcdef1", source: "git", commit: null }))).toBe("abcdef1");
  });

  it("shows a git version when the commit is missing or not hex", () => {
    expect(versionLabel(versionBody({
      version: "v1.2.3",
      commit: null,
      source: "git",
    }))).toBe("v1.2.3");
    for (const commit of ["not-a-commit", "zzabcdef123456", "abcdef123456xyz", "abc12"]) {
      expect(versionLabel(versionBody({ version: "v1.2.3", commit, source: "git" }))).toBe("v1.2.3");
    }
    expect(versionLabel(versionBody({
      version: "v1.2.3",
      commit: "  abc123def456  ",
      source: "git",
    }))).toBe("v1.2.3 · abc123d");
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

  it("shows a dev source with the fallback version and a short commit", async () => {
    fetchMock().mockResolvedValue(jsonResponse({
      version: "0.0.0+dev",
      commit: "abc123def456",
      source: "dev",
    }));
    await loadVersion();
    expect(el("app-version").hidden).toBe(false);
    expect(el("about-version").textContent).toBe("v0.0.0+dev · abc123d");
    expect(el("app-version").textContent).toBe("App version v0.0.0+dev · abc123d");
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

  async function expectUnavailable(): Promise<void> {
    await expect(loadVersion()).resolves.toBeUndefined();
    expect(el("app-version").hidden).toBe(true);
    expect(el("app-version").textContent).toBe("");
    expect(el("about-version").textContent).toBe("Version unavailable");
    expect(VERSION_UNAVAILABLE).toBe("Version unavailable");
  }

  it("shows unavailable for a 500 that still has a version body", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody({ version: "v9.9.9" }), false));
    await expectUnavailable();
    expect(document.body.textContent).not.toContain("v9.9.9");
  });

  it("shows unavailable for malformed JSON, a null or string body, a bad source, a numeric commit, or a blank version", async () => {
    const raw = "Unexpected token < in JSON";
    fetchMock().mockResolvedValue({
      ok: true,
      json: async () => {
        throw new SyntaxError(raw);
      },
    } as unknown as Response);
    await expectUnavailable();
    expect(document.body.textContent).not.toContain(raw);

    const bodies: unknown[] = [
      null,
      "v1.4.2",
      { version: "v1.4.2", commit: "abc123def456", source: "nightly" },
      { version: "v1.4.2", commit: 1234567, source: "release" },
      { version: "   ", commit: null, source: "dev" },
      { version: "", commit: null, source: "release" },
    ];
    for (const body of bodies) {
      fetchMock().mockResolvedValue(jsonResponse(body));
      await expectUnavailable();
    }
    expect(document.body.textContent).not.toContain("nightly");
    expect(document.body.textContent).not.toContain("1234567");
  });

  it("drops a version that was already showing when a later load fails", async () => {
    fetchMock().mockResolvedValueOnce(jsonResponse(versionBody({ version: "v3.3.3" })));
    await loadVersion();
    expect(el("about-version").textContent).toBe("v3.3.3");
    expect(el("app-version").hidden).toBe(false);
    fetchMock().mockResolvedValueOnce(jsonResponse({ error: "disk I/O" }, false));
    await expectUnavailable();
    expect(document.body.textContent).not.toContain("v3.3.3");
    expect(document.body.textContent).not.toContain("disk I/O");
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    await expect(copyVersion()).resolves.toBeUndefined();
    expect(writeText).not.toHaveBeenCalled();
    expect(el("version-copy-status").textContent).toBe("Version unavailable");
  });

  it("says the copy failed when the clipboard API is missing or the page is not a secure context", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody()));
    await loadVersion();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    await expect(copyVersion()).resolves.toBeUndefined();
    expect(el("version-copy-status").textContent).toBe("Couldn't copy the version.");

    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    await expect(copyVersion()).resolves.toBeUndefined();
    expect(writeText).not.toHaveBeenCalled();
    expect(el("version-copy-status").textContent).toBe("Couldn't copy the version.");
  });

  it("clears Copied when the version reloads", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody()));
    await loadVersion();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    await copyVersion();
    expect(el("version-copy-status").textContent).toBe("Copied");
    fetchMock().mockResolvedValue(jsonResponse(versionBody({ version: "v2.0.0" })));
    await loadVersion();
    expect(el("version-copy-status").textContent).toBe("");
    expect(el("about-version").textContent).toBe("v2.0.0");
    expect(el("app-version").textContent).toBe("App version v2.0.0");
    expect(el("app-version").querySelectorAll("span")).toHaveLength(2);
  });

  it("shows a git version without a null or non-hex commit", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody({
      version: "v1.2.3",
      commit: null,
      source: "git",
    })));
    await loadVersion();
    expect(el("app-version").hidden).toBe(false);
    expect(el("about-version").textContent).toBe("v1.2.3");
    fetchMock().mockResolvedValue(jsonResponse(versionBody({
      version: "v1.2.3",
      commit: "not-a-commit",
      source: "git",
    })));
    await loadVersion();
    expect(el("about-version").textContent).toBe("v1.2.3");
    expect(el("app-version").textContent).not.toContain("not-a-commit");
  });

  it("shows an XSS version string as text and does not create an image", async () => {
    const hostile = "<img src=x onerror=alert(1)>";
    fetchMock().mockResolvedValue(jsonResponse(versionBody({ version: hostile })));
    await loadVersion();
    expect(document.querySelector("img")).toBeNull();
    expect(el("about-version").querySelector("img")).toBeNull();
    expect(el("app-version").querySelector("img")).toBeNull();
    expect(el("about-version").children).toHaveLength(0);
    expect(el("about-version").textContent).toBe(hostile);
    expect(el("app-version").textContent).toBe(`App version ${hostile}`);
  });

  it("getVersion rejects a null body and a blank version", async () => {
    fetchMock().mockResolvedValue(jsonResponse(null));
    await expect(getVersion()).rejects.toThrow(/^Version unavailable$/);

    fetchMock().mockResolvedValue(jsonResponse({
      version: "   ",
      commit: null,
      source: "dev",
    }));
    await expect(getVersion()).rejects.toThrow(/^Version unavailable$/);
  });

  it("trims a padded version on the page and in the client", async () => {
    fetchMock().mockResolvedValue(jsonResponse(versionBody({ version: "  v8.8.8  " })));
    await expect(getVersion()).resolves.toMatchObject({ version: "v8.8.8", source: "release" });
    await loadVersion();
    expect(el("about-version").textContent).toBe("v8.8.8");
    expect(el("app-version").textContent).toBe("App version v8.8.8");
  });

  it("has nothing to copy before a version loads", async () => {
    vi.resetModules();
    const fresh = await import("./version");
    installPage();
    fresh.wireVersion();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    await expect(fresh.copyVersion()).resolves.toBeUndefined();
    expect(writeText).not.toHaveBeenCalled();
    expect(el("version-copy-status").textContent).toBe("Version unavailable");
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
