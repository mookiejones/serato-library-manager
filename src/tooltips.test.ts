// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SHORTCUTS, shortcutKeys } from "./shortcuts";
import { installPage } from "./test-page";
import { TIP_SHORTCUTS, tip, tips, type TipKey } from "./tips";
import { controlsMissingTip, unknownTips, untippedControls } from "./tooltip-audit";
import { SHOW_DELAY_MS, wireTooltips } from "./tooltips";

const sources = import.meta.glob("./*.ts", { eager: true, query: "?raw", import: "default" });

function tooltip(): HTMLElement {
  return document.getElementById("control-tooltip")!;
}

function hover(node: Element): void {
  node.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
}

function button(key: TipKey): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = "Label";
  tip(node, key);
  document.body.append(node);
  return node;
}

describe("every control has a tooltip", () => {
  beforeEach(() => installPage());

  it("covers every control in index.html", () => {
    expect(untippedControls(document).map((node) => node.outerHTML)).toEqual([]);
  });

  it("uses only known tip keys in index.html", () => {
    expect(unknownTips(document)).toEqual([]);
  });

  it("fails for a control added without a tooltip", () => {
    const naked = document.createElement("button");
    document.body.append(naked);
    expect(untippedControls(document)).toEqual([naked]);
  });

  it("fails for a tip key that has no text", () => {
    const wrong = document.createElement("button");
    wrong.dataset.tip = "notAKey";
    document.body.append(wrong);
    expect(unknownTips(document)).toEqual(["notAKey"]);
  });

  it("does not ask for a tooltip on the hidden file picker", () => {
    expect(untippedControls(document)).not.toContain(document.getElementById("import-file"));
  });

  it("covers every control built in TypeScript", () => {
    const gaps = Object.entries(sources)
      .filter(([path]) => !path.endsWith(".test.ts") && !path.endsWith("tooltip-audit.ts"))
      .flatMap(([path, source]) => controlsMissingTip(source).map((name) => `${path}: ${name}`));
    expect(gaps).toEqual([]);
  });
});

describe("controlsMissingTip", () => {
  it("names a control with no tip call", () => {
    expect(controlsMissingTip('const save = document.createElement("button");')).toEqual(["save"]);
  });

  it("accepts a control with a tip call", () => {
    expect(controlsMissingTip('const save = document.createElement("button");\ntip(save, "trackSave");')).toEqual([]);
  });

  it("checks each declaration of a reused name on its own", () => {
    const source = [
      'const save = document.createElement("button");',
      'tip(save, "trackSave");',
      'const save = document.createElement("button");',
    ].join("\n");
    expect(controlsMissingTip(source)).toEqual(["save"]);
  });

  it("reads a control picked by a ternary", () => {
    const source = 'const input = wide\n  ? document.createElement("textarea")\n  : document.createElement("input");';
    expect(controlsMissingTip(source)).toEqual(["input"]);
  });

  it("reads a control assigned without a declaration", () => {
    expect(controlsMissingTip('  nextNode = document.createElement("button");')).toEqual(["nextNode"]);
  });

  it("reads a control on a class field", () => {
    const source = '    this.zoom = document.createElement("button");\n    tip(this.zoom, "reload");';
    expect(controlsMissingTip(source)).toEqual([]);
  });

  it("reads a div given a slider role", () => {
    expect(controlsMissingTip('    this.hit.setAttribute("role", "slider");')).toEqual(["this.hit"]);
  });

  it("reads a row given an option role", () => {
    const source = 'const row = document.createElement("div");\nrow.setAttribute("role", "option");\ntip(row, "trackRow");';
    expect(controlsMissingTip(source)).toEqual([]);
  });

  it("ignores elements that are not controls", () => {
    expect(controlsMissingTip('const row = document.createElement("div");')).toEqual([]);
  });
});

describe("tip text", () => {
  it("is plain sentences", () => {
    for (const [key, text] of Object.entries(tips)) {
      expect(text, key).toMatch(/^[A-Z].*\.$/);
      expect(text.length, key).toBeLessThanOrEqual(90);
    }
  });

  it("names only shortcuts in the shortcut table", () => {
    const ids = SHORTCUTS.map((shortcut) => shortcut.id as string);
    for (const id of Object.values(TIP_SHORTCUTS).flat()) expect(ids).toContain(id);
  });

  it("gives search both of its keys", () => {
    expect(shortcutKeys("focus-search")).toBe("Ctrl/Cmd+F or /");
  });

  it("returns nothing for an unknown shortcut", () => {
    expect(shortcutKeys("no-such-shortcut")).toBeNull();
  });
});

describe("tip", () => {
  it("does not name a row that fills in its text later", () => {
    const row = document.createElement("div");
    tip(row, "trackRow");
    row.textContent = "Night Drive";
    expect(row.hasAttribute("aria-label")).toBe(false);
  });

  it("does not replace the label of a field", () => {
    const label = document.createElement("label");
    label.textContent = "Title";
    const input = document.createElement("input");
    tip(input, "trackTitle");
    label.append(input);
    expect(input.hasAttribute("aria-label")).toBe(false);
  });

  it("keeps an aria-label that is already there", () => {
    const named = document.createElement("input");
    named.setAttribute("aria-label", "Track.mp3");
    tip(named, "filesSelect");
    expect(named.getAttribute("aria-label")).toBe("Track.mp3");
  });
});

describe("showing a tooltip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.replaceChildren();
    wireTooltips(shortcutKeys);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits, then shows the text on hover", () => {
    const control = button("reload");
    hover(control);
    expect(tooltip().hidden).toBe(true);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().hidden).toBe(false);
    expect(tooltip().textContent).toBe(tips.reload);
    expect(tooltip().getAttribute("role")).toBe("tooltip");
  });

  it("does not show when the pointer leaves first", () => {
    const control = button("reload");
    hover(control);
    control.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().hidden).toBe(true);
  });

  it("shows the keys from the shortcut table", () => {
    const control = button("search");
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().textContent).toBe(`${tips.search}Ctrl/Cmd+F or /`);
  });

  it("leaves out the keys when the table has no such shortcut", () => {
    wireTooltips(() => null);
    const control = button("search");
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().textContent).toBe(tips.search);
  });

  it("joins two shortcuts for one control", () => {
    const control = button("playerSeek");
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().textContent).toBe(`${tips.playerSeek}Left arrow or Right arrow`);
  });

  it("puts the detail ahead of the tip", () => {
    const control = document.createElement("button");
    tip(control, "filesSelect", "/Music/Sets");
    document.body.append(control);
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().textContent).toBe(`/Music/Sets${tips.filesSelect}`);
  });

  it("shows on keyboard focus and describes the control at once", () => {
    const control = button("reload");
    control.matches = (selector: string) => selector === ":focus-visible";
    control.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(control.getAttribute("aria-describedby")).toBe("control-tooltip");
    expect(tooltip().textContent).toBe(tips.reload);
    expect(tooltip().hidden).toBe(true);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().hidden).toBe(false);
  });

  it("does not show when a mouse click moved focus", () => {
    const control = button("reload");
    control.matches = () => false;
    control.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().hidden).toBe(true);
  });

  it("hides on blur and clears the description", () => {
    const control = button("reload");
    control.matches = (selector: string) => selector === ":focus-visible";
    control.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    control.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    expect(tooltip().hidden).toBe(true);
    expect(control.hasAttribute("aria-describedby")).toBe(false);
  });

  it("keeps a description the control already had", () => {
    const control = button("reload");
    control.setAttribute("aria-describedby", "help");
    hover(control);
    expect(control.getAttribute("aria-describedby")).toBe("help control-tooltip");
    control.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
    expect(control.getAttribute("aria-describedby")).toBe("help");
  });

  it.each([
    ["a key press", () => document.body.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }))],
    ["a click", () => document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }))],
    ["a press", () => document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }))],
    ["a scroll", () => document.body.dispatchEvent(new Event("scroll"))],
  ])("hides on %s", (_name, act) => {
    hover(button("reload"));
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    act();
    expect(tooltip().hidden).toBe(true);
  });

  it("does not stop Esc from reaching the page", () => {
    hover(button("reload"));
    const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Escape" });
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("reads the checkbox tip when the label text is hovered", () => {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    tip(box, "rekordboxMemory");
    const text = document.createElement("span");
    label.append(box, text);
    document.body.append(label);
    hover(text);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().textContent).toBe(tips.rekordboxMemory);
  });

  it("hides when the pointer reaches something without a tip", () => {
    hover(button("reload"));
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    hover(document.body);
    expect(tooltip().hidden).toBe(true);
  });

  it("moves into an open dialog so the top layer does not cover it", () => {
    const dialog = document.createElement("dialog");
    const control = document.createElement("button");
    tip(control, "reload");
    dialog.append(control);
    document.body.append(dialog);
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().parentElement).toBe(dialog);
  });

  it("does not show for a control removed before the delay ends", () => {
    const control = button("reload");
    hover(control);
    control.remove();
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().hidden).toBe(true);
  });

  it("stays on screen near the right edge", () => {
    const control = button("reload");
    control.getBoundingClientRect = () => new DOMRect(window.innerWidth - 4, 10, 4, 20);
    tooltip().getBoundingClientRect = () => new DOMRect(0, 0, 200, 40);
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().style.left).toBe(`${window.innerWidth - 208}px`);
    expect(tooltip().style.top).toBe("36px");
  });

  it("opens above a control at the bottom of the window", () => {
    const control = button("reload");
    control.getBoundingClientRect = () => new DOMRect(20, window.innerHeight - 24, 40, 20);
    tooltip().getBoundingClientRect = () => new DOMRect(0, 0, 200, 40);
    hover(control);
    vi.advanceTimersByTime(SHOW_DELAY_MS);
    expect(tooltip().style.left).toBe("20px");
    expect(tooltip().style.top).toBe(`${window.innerHeight - 70}px`);
  });
});
