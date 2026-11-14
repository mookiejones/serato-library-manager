import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TagClusterPlan, TagClusters } from "../lib/api-types";
import { bridge } from "../lib/bridge";
import { setLocale } from "../lib/i18n";
import { state } from "../lib/state";
import { getTagsSnapshot, loadTags, repaintTags, unmountTags, wireTags } from "../lib/health/tags";
import { groupChanges, previewLines, tagsSummary, titlesSummary } from "../lib/health/tags-view";
import { drainReactScheduler, installPage } from "./test-page";
import { applyStaticTooltips } from "../lib/ui/tooltip";
import { getNotice, resetNotice } from "../lib/ui/notice-store";

const postJSON = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, postJSON };
});

const groups: TagClusters = {
  field: "genre",
  values: 4,
  groups: [
    {
      key: "hiphop",
      suggested: "Hip Hop",
      tracks: 5,
      spellings: [
        { value: "Hip Hop", count: 3 },
        { value: "Hip-Hop", count: 2 },
      ],
    },
    {
      key: "rnb",
      suggested: "R&B",
      tracks: 2,
      spellings: [
        { value: "R&B", count: 1 },
        { value: "rnb", count: 1 },
      ],
    },
  ],
};

const clear: TagClusters = { field: "genre", values: 3, groups: [] };

const preview: TagClusterPlan = {
  field: "genre",
  value: "Hip Hop",
  key: "hiphop",
  written: false,
  changes: [
    { id: 1, from: "Hip-Hop", to: "Hip Hop" },
    { id: 2, from: "Hip-Hop", to: "Hip Hop" },
  ],
};

const titlePreview: TagClusterPlan = {
  field: "name",
  value: "titles",
  key: "clean",
  written: false,
  changes: [
    { id: 1, from: "01 - TRACK (Original Mix) http://x", to: "Track" },
    {
      id: 2,
      from: "Song feat. Guest",
      to: "Song",
      remixer: "Guest",
    },
  ],
};

const emptyMapping: TagClusterPlan = {
  field: "mappings",
  value: "saved",
  key: "saved",
  written: false,
  changes: [],
};

const mappingPreview: TagClusterPlan = {
  field: "mappings",
  value: "saved",
  key: "saved",
  written: false,
  changes: [
    { id: 10, from: "Hip-Hop", to: "Hip Hop", field: "genre" },
    { id: 11, from: "dj shadow", to: "DJ Shadow", field: "artist" },
  ],
};

function postAction(body: unknown): string {
  if (typeof body === "object" && body !== null && "action" in body) {
    return String((body as { action: unknown }).action);
  }
  return "";
}

function stubPosts(handlers: Record<string, unknown> = {}): void {
  postJSON.mockImplementation(async (_url: string, body: unknown) => {
    const action = postAction(body);
    if (Object.prototype.hasOwnProperty.call(handlers, action)) {
      const value = handlers[action];
      if (value instanceof Error) throw value;
      return value;
    }
    if (action === "refresh-preview") return emptyMapping;
    throw new Error(`unexpected postJSON action ${action}`);
  });
}

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function reportText(): string {
  return document.getElementById("tags-report")!.textContent || "";
}

function applyFor(key: string): HTMLButtonElement {
  return document.querySelector(`[data-tags-action="apply"][data-key="${key}"]`) as HTMLButtonElement;
}

function previewFor(key: string): HTMLButtonElement {
  return document.querySelector(`[data-tags-action="preview"][data-key="${key}"]`) as HTMLButtonElement;
}

describe("tag spelling helpers", () => {
  it("collapses the same from→to pair and keeps different pairs", () => {
    expect(groupChanges([
      { id: 1, from: "Hip-Hop", to: "Hip Hop" },
      { id: 2, from: "Hip-Hop", to: "Hip Hop" },
      { id: 3, from: "hiphop", to: "Hip Hop" },
    ])).toEqual([
      { from: "Hip-Hop", to: "Hip Hop", count: 2 },
      { from: "hiphop", to: "Hip Hop", count: 1 },
    ]);
  });

  it("names an empty genre space", () => {
    setLocale("en");
    expect(tagsSummary("genre", 8, 0)).toBe("Every genre in this space uses one spelling.");
    expect(previewLines(preview.changes)).toEqual(["Hip-Hop → Hip Hop (2 tracks)"]);
  });

  it("keeps remixer pairs separate and names a title cleanup", () => {
    setLocale("en");
    expect(groupChanges(titlePreview.changes)).toEqual([
      { from: "01 - TRACK (Original Mix) http://x", to: "Track", count: 1 },
      { from: "Song feat. Guest", to: "Song", count: 1, remixer: "Guest" },
    ]);
    expect(previewLines(titlePreview.changes)).toEqual([
      "01 - TRACK (Original Mix) http://x → Track (1 track)",
      "Song feat. Guest → Song, remixer Guest (1 track)",
    ]);
    expect(titlesSummary(0)).toBe("Every title in this space already matches the cleanup rules.");
    expect(titlesSummary(2)).toBe("2 titles in this space would change.");
  });

  it("keeps mapping pairs on different fields separate", () => {
    setLocale("en");
    expect(groupChanges(mappingPreview.changes)).toEqual([
      { from: "Hip-Hop", to: "Hip Hop", count: 1, field: "genre" },
      { from: "dj shadow", to: "DJ Shadow", count: 1, field: "artist" },
    ]);
    expect(previewLines(mappingPreview.changes)).toEqual([
      "Genre: Hip-Hop → Hip Hop (1 track)",
      "Artist: dj shadow → DJ Shadow (1 track)",
    ]);
  });
});

describe("tags", () => {
  beforeEach(() => {
    installPage();
    setLocale("en");
    state.space = "Serato Library";
    state.writable = true;
    postJSON.mockReset();
    stubPosts();
    bridge.reloadLibrary = vi.fn(async () => {});
    bridge.lockDown = vi.fn();
    wireTags();
    document.getElementById("tags-panel")!.hidden = false;
  });

  afterEach(async () => {
    unmountTags();
    resetNotice();
    await drainReactScheduler();
    vi.unstubAllGlobals();
    setLocale("en");
  });

  it("asks for the space field and paints groups", async () => {
    const fetchMock = vi.fn(async () => reply(groups));
    vi.stubGlobal("fetch", fetchMock);
    await loadTags();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tag-clusters?space=Serato%20Library&field=genre",
    );
    expect(document.getElementById("tags-scope")!.textContent).toBe("Whole space");
    expect(reportText()).toContain("4 genre spellings in this space. 2 groups");
    expect(reportText()).toContain("Hip Hop");
    expect(reportText()).toContain("Hip-Hop");
    expect(reportText()).toContain("Suggested");
    expect(applyFor("hiphop").disabled).toBe(true);
    expect(document.getElementById("tags-refresh")!.getAttribute("aria-busy")).toBe("false");
  });

  it("asks for artist when that field is pressed", async () => {
    const fetchMock = vi.fn(async () => reply({ ...groups, field: "artist" }));
    vi.stubGlobal("fetch", fetchMock);
    document.getElementById("tags-artist")!.click();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await vi.waitFor(() => {
      expect(document.getElementById("tags-artist")!.getAttribute("aria-busy")).toBe("false");
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tag-clusters?space=Serato%20Library&field=artist",
    );
  });

  it("previews titles without asking for spelling groups", async () => {
    const fetchMock = vi.fn(async () => reply(groups));
    vi.stubGlobal("fetch", fetchMock);
    stubPosts({ "clean-preview": titlePreview });
    document.getElementById("tags-titles")!.click();
    await vi.waitFor(() => expect(postJSON).toHaveBeenCalled());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "clean-preview",
      space: "Serato Library",
    });
    expect(reportText()).toContain("2 titles in this space would change.");
    expect(reportText()).toContain("Song feat. Guest → Song, remixer Guest (1 track)");
    expect(document.getElementById("tags-hint")!.textContent).toContain("Strips track numbers");
    expect(document.querySelector<HTMLButtonElement>('[data-tags-action="clean-apply"]')!.disabled).toBe(false);
  });

  it("disables title Apply when nothing would change", async () => {
    stubPosts({ "clean-preview": { ...titlePreview, changes: [] } });
    document.getElementById("tags-titles")!.click();
    await vi.waitFor(() => expect(postJSON).toHaveBeenCalled());
    expect(reportText()).toContain("Every title in this space already matches the cleanup rules.");
    expect(document.querySelector<HTMLButtonElement>('[data-tags-action="clean-apply"]')!.disabled).toBe(true);
  });

  it("applies cleaned titles, reloads the library, and shows the written sentence", async () => {
    stubPosts({
      "clean-preview": titlePreview,
      "clean-apply": { ...titlePreview, written: true },
    });
    document.getElementById("tags-titles")!.click();
    await vi.waitFor(() => expect(document.querySelector('[data-tags-action="clean-apply"]')).not.toBeNull());
    document.querySelector<HTMLButtonElement>('[data-tags-action="clean-apply"]')!.click();
    await vi.waitFor(() => expect(bridge.reloadLibrary).toHaveBeenCalled());
    expect(postJSON.mock.calls.filter((call) => postAction(call[1]) === "clean-apply")).toHaveLength(1);
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "clean-apply",
      space: "Serato Library",
    });
    expect(document.getElementById("tags-status")!.textContent).toContain("Wrote the cleaned titles on 2 tracks");
  });

  it("locks the page on a 409 from title apply", async () => {
    const locked = Object.assign(new Error("Quit Serato DJ before writing."), {
      status: 409,
      payload: { error: "Quit Serato DJ before writing.", serato: { writable: false } },
    });
    stubPosts({
      "clean-preview": titlePreview,
      "clean-apply": locked,
    });
    document.getElementById("tags-titles")!.click();
    await vi.waitFor(() => expect(document.querySelector('[data-tags-action="clean-apply"]')).not.toBeNull());
    bridge.lockDown = vi.fn(() => {
      state.writable = false;
    });
    document.querySelector<HTMLButtonElement>('[data-tags-action="clean-apply"]')!.click();
    await vi.waitFor(() => expect(bridge.lockDown).toHaveBeenCalled());
    expect(document.getElementById("tags-status")!.textContent).toContain("Quit Serato DJ before writing.");
    expect(document.querySelector<HTMLButtonElement>('[data-tags-action="clean-apply"]')!.disabled).toBe(true);
    expect(getNotice()).toEqual({
      text: "Quit Serato DJ before writing.",
      severity: "error",
    });
  });

  it("shows a clean report when every spelling is unique", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(clear)));
    await loadTags();
    expect(reportText()).toContain("Every genre in this space uses one spelling.");
    expect(reportText()).not.toContain("Hip-Hop");
  });

  it("ignores a late reply after a newer check started", async () => {
    let finish: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const first = loadTags();
    const firstFinish = finish;
    const second = loadTags();
    finish(reply(clear));
    await second;
    firstFinish(reply(groups));
    await first;
    expect(reportText()).toContain("Every genre in this space uses one spelling.");
    expect(reportText()).not.toContain("Hip-Hop");
  });

  it("ignores a late reply after the panel unmounts", async () => {
    let finish: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = loadTags();
    unmountTags();
    expect(document.getElementById("tags-report")).toBeNull();
    expect(getTagsSnapshot().tagsBusy).toBe(false);
    finish(reply(groups));
    await expect(pending).resolves.toBeUndefined();
    expect(getTagsSnapshot().tagsBusy).toBe(false);
  });

  it("shows the server error sentence when the groups cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ error: "Choose genre or artist.", code: "choose_genre_or_artist" }, 400)));
    await loadTags();
    expect(document.getElementById("tags-status")!.textContent).toBe("Choose genre or artist.");
    expect(document.activeElement).toBe(document.getElementById("tags-refresh"));
  });

  it("shows the unreachable sentence when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await loadTags();
    expect(document.getElementById("tags-status")!.textContent).toContain("Couldn't reach the library server");
  });

  it("reviews a spelling then enables Apply when the radio still matches", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    stubPosts({ preview });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(postJSON).toHaveBeenCalled());
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "preview",
      space: "Serato Library",
      field: "genre",
      value: "Hip Hop",
    });
    expect(document.getElementById("tags-status")!.textContent).toContain("2 tracks would become Hip Hop");
    expect(reportText()).toContain("Hip-Hop → Hip Hop (2 tracks)");
    expect(applyFor("hiphop").disabled).toBe(false);
  });

  it("disables Apply when the radio no longer matches the preview", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    stubPosts({ preview });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(applyFor("hiphop").disabled).toBe(false));
    const other = document.querySelector<HTMLInputElement>("input[name='tags-hiphop'][value='Hip-Hop']")!;
    other.click();
    expect(applyFor("hiphop").disabled).toBe(true);
  });

  it("disables Apply while the library is locked", async () => {
    state.writable = false;
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    stubPosts({ preview });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(postJSON).toHaveBeenCalled());
    expect(applyFor("hiphop").disabled).toBe(true);
  });

  it("applies the preview, reloads the library, and shows the written sentence", async () => {
    const fetchMock = vi.fn(async () => reply(groups));
    vi.stubGlobal("fetch", fetchMock);
    stubPosts({
      preview,
      apply: { ...preview, written: true },
    });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(applyFor("hiphop").disabled).toBe(false));
    applyFor("hiphop").click();
    await vi.waitFor(() => expect(bridge.reloadLibrary).toHaveBeenCalled());
    expect(postJSON.mock.calls.filter((call) => postAction(call[1]) === "apply")).toHaveLength(1);
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "apply",
      space: "Serato Library",
      field: "genre",
      value: "Hip Hop",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(document.getElementById("tags-status")!.textContent).toContain("Wrote Hip Hop on 2 tracks");
  });

  it("locks the page on a 409 and disables Apply", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    const locked = Object.assign(new Error("Quit Serato DJ before writing."), {
      status: 409,
      payload: { error: "Quit Serato DJ before writing.", serato: { writable: false } },
    });
    stubPosts({
      preview,
      apply: locked,
    });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(applyFor("hiphop").disabled).toBe(false));
    bridge.lockDown = vi.fn(() => {
      state.writable = false;
    });
    applyFor("hiphop").click();
    await vi.waitFor(() => expect(bridge.lockDown).toHaveBeenCalled());
    expect(document.getElementById("tags-status")!.textContent).toContain("Quit Serato DJ before writing.");
    expect(applyFor("hiphop").disabled).toBe(true);
  });

  it("shows a write failure on the status line and as an error notice", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    const failed = Object.assign(
      new Error(
        "Could not put master.sqlite back. Open the local log from Settings, or read the operation log on Backups.",
      ),
      {
        status: 500,
        payload: {
          error:
            "Could not put master.sqlite back. Open the local log from Settings, or read the operation log on Backups.",
          code: "restore_outside",
          params: { name: "master.sqlite" },
        },
      },
    );
    stubPosts({
      preview,
      apply: failed,
    });
    await loadTags();
    previewFor("hiphop").click();
    await vi.waitFor(() => expect(applyFor("hiphop").disabled).toBe(false));
    applyFor("hiphop").click();
    await vi.waitFor(() =>
      expect(document.getElementById("tags-status")!.textContent).toContain("master.sqlite"),
    );
    expect(document.getElementById("tags-status")!.textContent).toContain("local log");
    expect(getNotice()).toEqual({
      text: failed.message,
      severity: "error",
    });
    expect(bridge.lockDown).not.toHaveBeenCalled();
  });

  it("repaints the last report on a language change without asking the server again", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(reply(groups)));
    vi.stubGlobal("fetch", fetchMock);
    await loadTags();
    setLocale("es");
    repaintTags();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(reportText()).toContain("grafías de género");
    expect(reportText()).not.toContain("genre spellings");
    expect(document.getElementById("tags-scope")!.textContent).toBe("Todo el espacio");
  });

  it("asks for saved mappings on genre load and hides the banner when none are pending", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    await loadTags();
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "refresh-preview",
      space: "Serato Library",
    });
    expect(reportText()).not.toContain("saved spelling");
    expect(document.querySelector('[data-tags-action="refresh-apply"]')).toBeNull();
  });

  it("shows Apply saved mappings when later rows still use a saved spelling", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    stubPosts({ "refresh-preview": mappingPreview });
    await loadTags();
    expect(reportText()).toContain("2 tracks still use a saved spelling.");
    expect(reportText()).toContain("Genre: Hip-Hop → Hip Hop (1 track)");
    expect(reportText()).toContain("Artist: dj shadow → DJ Shadow (1 track)");
    expect(document.querySelector<HTMLButtonElement>('[data-tags-action="refresh-apply"]')!.disabled).toBe(false);
  });

  it("skips mapping preview on Titles", async () => {
    const fetchMock = vi.fn(async () => reply(groups));
    vi.stubGlobal("fetch", fetchMock);
    stubPosts({ "clean-preview": titlePreview });
    document.getElementById("tags-titles")!.click();
    await vi.waitFor(() => expect(postJSON).toHaveBeenCalled());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(postJSON).not.toHaveBeenCalledWith("/api/tag-clusters", {
      action: "refresh-preview",
      space: "Serato Library",
    });
    expect(document.querySelector('[data-tags-action="refresh-apply"]')).toBeNull();
  });

  it("treats a missing or failed mapping preview as no banner", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    postJSON.mockRejectedValue(new Error("boom"));
    await loadTags();
    expect(reportText()).toContain("Hip Hop");
    expect(document.querySelector('[data-tags-action="refresh-apply"]')).toBeNull();
    stubPosts({ "refresh-preview": { field: "mappings" } });
    await loadTags();
    expect(document.querySelector('[data-tags-action="refresh-apply"]')).toBeNull();
  });

  it("applies saved mappings, reloads the library, and shows the written sentence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    let pending: TagClusterPlan = mappingPreview;
    postJSON.mockImplementation(async (_url: string, body: unknown) => {
      const action = postAction(body);
      if (action === "refresh-preview") return pending;
      if (action === "refresh-apply") {
        pending = emptyMapping;
        return { ...mappingPreview, written: true };
      }
      throw new Error(`unexpected postJSON action ${action}`);
    });
    await loadTags();
    document.querySelector<HTMLButtonElement>('[data-tags-action="refresh-apply"]')!.click();
    await vi.waitFor(() => expect(bridge.reloadLibrary).toHaveBeenCalled());
    expect(postJSON.mock.calls.filter((call) => postAction(call[1]) === "refresh-apply")).toHaveLength(1);
    expect(postJSON).toHaveBeenCalledWith("/api/tag-clusters", {
      action: "refresh-apply",
      space: "Serato Library",
    });
    expect(document.getElementById("tags-status")!.textContent).toContain("Wrote saved spellings on 2 tracks");
    expect(document.querySelector('[data-tags-action="refresh-apply"]')).toBeNull();
  });

  it("locks the page on a 409 from mapping apply", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    const locked = Object.assign(new Error("Quit Serato DJ before writing."), {
      status: 409,
      payload: { error: "Quit Serato DJ before writing.", serato: { writable: false } },
    });
    stubPosts({
      "refresh-preview": mappingPreview,
      "refresh-apply": locked,
    });
    await loadTags();
    bridge.lockDown = vi.fn(() => {
      state.writable = false;
    });
    document.querySelector<HTMLButtonElement>('[data-tags-action="refresh-apply"]')!.click();
    await vi.waitFor(() => expect(bridge.lockDown).toHaveBeenCalled());
    expect(document.getElementById("tags-status")!.textContent).toContain("Quit Serato DJ before writing.");
    expect(document.querySelector<HTMLButtonElement>('[data-tags-action="refresh-apply"]')!.disabled).toBe(true);
  });

  it("gives every tags control a tooltip", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(groups)));
    stubPosts({ "refresh-preview": mappingPreview });
    await loadTags();
    applyStaticTooltips();
    expect(document.getElementById("tags-genre")!.dataset.tooltipKey).toBe("tooltip.tagsGenre");
    expect(document.getElementById("tags-artist")!.dataset.tooltipKey).toBe("tooltip.tagsArtist");
    expect(document.getElementById("tags-titles")!.dataset.tooltipKey).toBe("tooltip.tagsTitles");
    expect(document.getElementById("tags-refresh")!.dataset.tooltipKey).toBe("tooltip.tagsRefresh");
    expect(document.querySelector<HTMLElement>('[data-view="tags"]')!.dataset.tooltipKey).toBe("tooltip.viewTags");
    expect(document.querySelector<HTMLElement>('[data-tags-action="refresh-apply"]')!.dataset.tooltipKey).toBe("tooltip.tagsApplyMappings");
    const untipped = [...document.querySelectorAll<HTMLElement>("#tags-panel button, #tags-panel input, #tags-panel summary")].filter(
      (node) => !node.dataset.tooltipKey,
    );
    expect(untipped).toEqual([]);
  });
});
