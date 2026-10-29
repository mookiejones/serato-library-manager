/**
 * Files view: music roots, breadcrumb, empty state, and a long folder.
 *
 * The rows are painted from state. A folder of more than 5000 entries is
 * virtualized, and the last entry can be scrolled to and opened.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FileEntry } from "./api-types";
import { bridge } from "./bridge";
import { wireDialogs } from "./dialogs";
import { libraryRootsFixture } from "./library-roots.fixture";
import { FILE_ROW, state } from "./state";
import { installPage } from "./test-page";
import { renderFiles, wireLibrary } from "./views";

const fetchMock = vi.fn();

function resetFiles(): void {
  state.mode = "files";
  state.writable = true;
  state.filesPath = "";
  state.filesParent = null;
  state.filesEntries = [];
  state.filesSelected = new Set();
  state.filesPick = null;
  state.filesPickPaths = [];
  state.filesPickSource = "";
  state.filesLoading = false;
  state.filesError = "";
  state.filesMessage = "";
  state.filesTruncated = false;
  state.filesAtRoots = false;
  state.filesRoots = [];
  state.filesRoot = null;
  state.filesBreadcrumb = [];
  state.filesElsewhere = false;
  state.filesActive = 0;
}

function indexes(): string[] {
  return [...document.querySelectorAll<HTMLElement>("#files-list [data-files-index]")].map(
    (node) => node.dataset.filesIndex ?? "",
  );
}

describe("files view", () => {
  beforeEach(() => {
    installPage();
    resetFiles();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    wireLibrary();
  });

  it("lists distinct labels with the path under each one", () => {
    state.filesAtRoots = true;
    state.filesRoots = libraryRootsFixture.roots.filter((root) => !root.missing);
    renderFiles();

    const rows = [...document.querySelectorAll<HTMLElement>("#files-list .files-row")].map((row) => row.textContent ?? "");
    expect(rows[0]).toContain("Home · /Music");
    expect(rows[0]).toContain("/Users/dj/Music");
    expect(rows[1]).toContain("GIGDRIVE · /Music");
    expect(rows[1]).toContain("/Volumes/GIGDRIVE/Music");
    expect(rows[0]).not.toBe(rows[1]);
    expect(document.querySelectorAll(".files-root-detail")).toHaveLength(2);
    expect(document.querySelectorAll(".files-icon-folder")).toHaveLength(2);
    expect(document.querySelector(".files-primary")).toBeNull();
    expect(document.querySelector("#files-elsewhere")?.textContent).toBe("Browse elsewhere…");
    expect(document.querySelector("#files-elsewhere")?.className).not.toContain("files-primary");
    expect((document.querySelector("#files-up") as HTMLButtonElement).disabled).toBe(true);
    expect(document.querySelector("#files-path [aria-current='page']")?.textContent).toBe("Music folders");

    const list = document.querySelector("#files-list") as HTMLElement;
    list.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement?.textContent).toContain("GIGDRIVE · /Music");
    list.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    expect(document.activeElement?.textContent).toContain("Home · /Music");
    expect(document.activeElement?.textContent).not.toContain("GIGDRIVE");
  });

  it("starts the breadcrumb at the root name and does not go above it", async () => {
    state.filesPath = "/music/House";
    state.filesParent = "/music";
    state.filesRoot = { name: "Music", path: "/music", kind: "folder" };
    state.filesBreadcrumb = [
      { name: "Music", path: "/music" },
      { name: "House", path: "/music/House" },
    ];
    state.filesEntries = [{ name: "a.mp3", kind: "file", path: "/music/House/a.mp3" }];
    renderFiles();

    expect((document.querySelector("#files-up") as HTMLButtonElement).disabled).toBe(false);
    const labels = [...document.querySelectorAll("#files-path .files-crumb")].map((node) => node.textContent);
    expect(labels).toEqual(["Music", "House"]);
    const buttons = [...document.querySelectorAll<HTMLButtonElement>("#files-path button")];
    expect(buttons).toHaveLength(1);
    expect(buttons[0]?.textContent).toBe("Music");

    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        path: "/music",
        parent: null,
        entries: [],
        elsewhere: false,
        root: { name: "Music", path: "/music", kind: "folder" },
        breadcrumb: [{ name: "Music", path: "/music" }],
        roots: [{ name: "Music", path: "/music", kind: "folder" }],
      }),
    });
    buttons[0]?.click();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = decodeURIComponent(String(fetchMock.mock.calls[0]?.[0]));
    expect(url).toContain("path=/music");
    expect(url).not.toContain("elsewhere");
    expect((document.querySelector("#files-up") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a missing drive and does not open it", async () => {
    state.filesAtRoots = true;
    state.filesRoots = libraryRootsFixture.roots.filter((root) => root.label !== "Home · /Music");
    renderFiles();
    const missing = document.querySelector("[aria-label='OLDDRIVE · /Music, Drive not connected']") as HTMLButtonElement;
    expect(missing.textContent).toContain("Drive not connected");
    expect(missing.textContent).toContain("/Volumes/OLDDRIVE/Music");
    expect(missing.getAttribute("aria-disabled")).toBe("true");
    expect(missing.closest(".files-row")?.classList.contains("is-missing")).toBe(true);
    missing.click();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refreshes the root list from GET /api/library-roots", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ telemetry_consent: false, wizard_complete: true }),
    });
    wireDialogs();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fetchMock.mockClear();
    state.filesAtRoots = true;
    state.filesRoots = libraryRootsFixture.roots;
    renderFiles();
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => libraryRootsFixture,
    });
    (document.querySelector("#files-refresh") as HTMLButtonElement).click();
    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls).toContain("/api/library-roots?refresh=1");
    });
  });

  it("uses Run setup as the only primary action when no roots exist", () => {
    state.filesAtRoots = true;
    const opened = vi.fn();
    bridge.openSetup = opened;
    renderFiles();

    const button = document.querySelector("#files-run-setup") as HTMLButtonElement;
    expect(button.textContent).toBe("Run setup");
    expect(document.querySelector("#files-list h2")?.textContent).toBe("No music folders yet");
    expect(document.querySelectorAll(".files-primary")).toHaveLength(1);
    expect(document.querySelector("#files-elsewhere")?.textContent).toBe("Browse elsewhere…");
    button.click();
    expect(opened).toHaveBeenCalledOnce();
  });

  it("asks to browse elsewhere only from the secondary link", async () => {
    wireDialogs();
    fetchMock.mockClear();
    state.filesAtRoots = true;
    state.filesRoots = [libraryRootsFixture.roots[0]!];
    renderFiles();
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        path: "/home/dj",
        parent: "/home",
        entries: [],
        elsewhere: true,
        breadcrumb: [{ name: "Home", path: "/home/dj" }],
        roots: [{ name: "Music", path: "/music", kind: "folder" }],
      }),
    });
    (document.querySelector("#files-elsewhere") as HTMLButtonElement).click();
    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls).toContain("/api/files?elsewhere=1");
    });
    await vi.waitFor(() => expect(document.querySelector("#files-path")?.textContent).toContain("Home"));
  });

  it("scrolls a folder of more than 5000 entries to the last one and opens it", async () => {
    const total = 5001;
    const entries: FileEntry[] = [];
    for (let index = 0; index < total; index += 1) {
      const name = `folder-${String(index).padStart(5, "0")}`;
      entries.push({ name, kind: "dir", path: `/music/crate/${name}` });
    }
    state.filesPath = "/music/crate";
    state.filesParent = "/music";
    state.filesRoot = { name: "Music", path: "/music", kind: "folder" };
    state.filesBreadcrumb = [
      { name: "Music", path: "/music" },
      { name: "crate", path: "/music/crate" },
    ];
    state.filesEntries = entries;
    renderFiles();

    const list = document.querySelector("#files-list") as HTMLElement;
    const spacer = list.querySelector(".files-spacer") as HTMLElement;
    expect(spacer.style.height).toBe(`${total * FILE_ROW}px`);
    expect(indexes()[0]).toBe("0");
    expect(indexes()).not.toContain(String(total - 1));
    expect(list.querySelectorAll(".files-row").length).toBeLessThan(80);
    expect(list.querySelector(".files-row")?.textContent).toContain("folder-00000");

    list.scrollTop = total * FILE_ROW;
    list.dispatchEvent(new Event("scroll"));
    const atEnd = indexes();
    const lastIndex = String(total - 1);
    expect(atEnd).toContain(lastIndex);
    expect(atEnd).not.toContain("0");
    const start = Number(atEnd[0]);
    const windowEl = list.querySelector(".files-window") as HTMLElement;
    expect(windowEl.style.transform).toBe(`translateY(${start * FILE_ROW}px)`);
    for (let index = start; index < total; index += 1) expect(atEnd).toContain(String(index));
    expect(list.querySelector(`[data-files-index="${lastIndex}"]`)?.textContent).toContain("folder-05000");

    list.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
    const last = document.activeElement as HTMLButtonElement;
    expect(last.dataset.filesIndex).toBe(lastIndex);
    expect(last.textContent).toContain("folder-05000");

    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        path: "/music/crate/folder-05000",
        parent: "/music/crate",
        entries: [{ name: "inside.mp3", kind: "file", path: "/music/crate/folder-05000/inside.mp3" }],
        elsewhere: false,
        root: { name: "Music", path: "/music", kind: "folder" },
        breadcrumb: [
          { name: "Music", path: "/music" },
          { name: "crate", path: "/music/crate" },
          { name: "folder-05000", path: "/music/crate/folder-05000" },
        ],
        roots: [{ name: "Music", path: "/music", kind: "folder" }],
      }),
    });
    last.click();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = decodeURIComponent(String(fetchMock.mock.calls[0]?.[0]));
    expect(url).toContain("path=/music/crate/folder-05000");
    await vi.waitFor(() => expect(document.querySelector("#files-path")?.textContent).toContain("folder-05000"));
    expect(document.querySelector("#files-list")?.textContent).toContain("inside.mp3");
  });
});
