import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clampWidth, mountSplitter, type Splitter } from "./splitter";

function sized(node: HTMLElement, prop: "clientWidth" | "offsetWidth", value: () => number): void {
  Object.defineProperty(node, prop, { configurable: true, get: value });
}

function pointer(type: string, clientX: number): Event {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX, button: 0 });
  Object.defineProperty(event, "pointerId", { value: 1 });
  return event;
}

describe("clampWidth", () => {
  it("keeps both panes at their minimum widths", () => {
    expect(clampWidth(100, 980, 360, 300)).toBe(360);
    expect(clampWidth(900, 980, 360, 300)).toBe(680);
    expect(clampWidth(500.4, 980, 360, 300)).toBe(500);
  });

  it("gives the first pane its minimum when there is no room for both", () => {
    expect(clampWidth(500, 500, 360, 300)).toBe(360);
  });
});

describe("mountSplitter", () => {
  let container: HTMLElement;
  let first: HTMLElement;
  let handle: HTMLElement;
  let room: number;
  let commits: (number | null)[];
  let splitter: Splitter;

  beforeEach(() => {
    room = 989;
    commits = [];
    container = document.createElement("div");
    first = document.createElement("section");
    handle = document.createElement("div");
    container.append(first, handle);
    document.body.append(container);
    sized(container, "clientWidth", () => room);
    sized(handle, "offsetWidth", () => 9);
    first.getBoundingClientRect = () => ({ width: 560 }) as DOMRect;
    splitter = mountSplitter({
      handle,
      container,
      first,
      property: "--track-list-width",
      minFirst: 360,
      minSecond: 300,
      onCommit: (width) => commits.push(width),
    });
  });

  afterEach(() => {
    container.remove();
  });

  it("starts on the default split and reports it", () => {
    expect(container.style.getPropertyValue("--track-list-width")).toBe("");
    expect(handle.getAttribute("aria-valuenow")).toBe("560");
    expect(handle.getAttribute("aria-valuemin")).toBe("360");
    expect(handle.getAttribute("aria-valuemax")).toBe("680");
  });

  it("moves with the arrow keys, Shift, Home, and End", () => {
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    expect(container.style.getPropertyValue("--track-list-width")).toBe("576px");
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", shiftKey: true }));
    expect(splitter.width()).toBe(512);
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "Home" }));
    expect(splitter.width()).toBe(360);
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }));
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "End" }));
    expect(splitter.width()).toBe(680);
    expect(commits).toEqual([576, 512, 360, 680]);
  });

  it("ignores other keys", () => {
    const event = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    handle.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(commits).toEqual([]);
  });

  it("drags and commits once when the pointer is released", () => {
    handle.dispatchEvent(pointer("pointerdown", 600));
    expect(handle.dataset.dragging).toBe("true");
    handle.dispatchEvent(pointer("pointermove", 520));
    handle.dispatchEvent(pointer("pointermove", 480));
    expect(container.style.getPropertyValue("--track-list-width")).toBe("440px");
    handle.dispatchEvent(pointer("pointerup", 480));
    expect(handle.dataset.dragging).toBeUndefined();
    expect(commits).toEqual([440]);
    handle.dispatchEvent(pointer("pointermove", 100));
    expect(splitter.width()).toBe(440);
  });

  it("does not commit a click without movement", () => {
    handle.dispatchEvent(pointer("pointerdown", 600));
    handle.dispatchEvent(pointer("pointerup", 600));
    expect(commits).toEqual([]);
  });

  it("resets to the default split on double-click", () => {
    splitter.set(500);
    handle.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    expect(container.style.getPropertyValue("--track-list-width")).toBe("");
    expect(splitter.width()).toBeNull();
    expect(commits).toEqual([null]);
  });

  it("keeps the chosen width while a narrow window clamps it", () => {
    splitter.set(650);
    room = 800;
    splitter.refit();
    expect(container.style.getPropertyValue("--track-list-width")).toBe("491px");
    expect(splitter.width()).toBe(650);
    room = 1400;
    splitter.refit();
    expect(container.style.getPropertyValue("--track-list-width")).toBe("650px");
    expect(commits).toEqual([]);
  });
});

describe("track list layout", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("applies the saved width and posts one change after a burst of keys", async () => {
    vi.useFakeTimers();
    const posts: unknown[] = [];
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
      posts.push(JSON.parse(String(init?.body)));
      return new Response("{}", { status: 200 });
    });
    const { installPage } = await import("./test-page");
    installPage();
    const sheet = document.querySelector<HTMLElement>(".sheet")!;
    sized(sheet, "clientWidth", () => 989);
    sized(document.getElementById("track-splitter")!, "offsetWidth", () => 9);
    const { applyLayout, wireLayout } = await import("./layout");
    wireLayout();
    applyLayout({ layout: { track_list_width: 500 } });
    expect(sheet.style.getPropertyValue("--track-list-width")).toBe("500px");

    const handle = document.getElementById("track-splitter")!;
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    expect(posts).toEqual([]);
    await vi.advanceTimersByTimeAsync(500);
    expect(posts).toEqual([{ layout: { track_list_width: 532 } }]);

    applyLayout({ layout: { track_list_width: 400 } });
    expect(sheet.style.getPropertyValue("--track-list-width")).toBe("532px");
  });
});
