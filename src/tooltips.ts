/**
 * The one tooltip on the page.
 *
 * A single element follows the control under the pointer or the keyboard
 * focus. Listeners sit on the document, so a row painted later needs only
 * its data-tip. The tooltip is linked to the control with aria-describedby
 * as soon as the control is reached. The delay holds back only the
 * picture, so a screen reader still has the text straight away.
 */

import { TIP_SHORTCUTS, tips, type TipKey } from "./tips";

/** Milliseconds before a tooltip appears, so a passing pointer shows none. */
export const SHOW_DELAY_MS = 500;

const TOOLTIP_ID = "control-tooltip";
const GAP_PX = 6;
const EDGE_PX = 8;

let keysFor: (id: string) => string | null = () => null;
let current: HTMLElement | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;

function tooltipNode(): HTMLElement {
  const found = document.getElementById(TOOLTIP_ID);
  if (found) return found;
  const node = document.createElement("div");
  node.id = TOOLTIP_ID;
  node.className = "tooltip";
  node.setAttribute("role", "tooltip");
  node.hidden = true;
  document.body.append(node);
  return node;
}

function line(className: string, text: string): HTMLSpanElement {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = text;
  return node;
}

function fill(node: HTMLElement, control: HTMLElement): void {
  const key = control.dataset.tip as TipKey;
  const shortcut = TIP_SHORTCUTS[key];
  const keys = [shortcut ?? []].flat().map(keysFor).filter(Boolean).join(" or ");
  const lines: HTMLSpanElement[] = [];
  if (control.dataset.tipDetail) lines.push(line("tooltip-detail", control.dataset.tipDetail));
  lines.push(line("tooltip-text", tips[key]));
  if (keys) lines.push(line("tooltip-keys", keys));
  node.replaceChildren(...lines);
}

function describe(control: HTMLElement): void {
  const ids = (control.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
  control.setAttribute("aria-describedby", [...ids, TOOLTIP_ID].join(" "));
}

function undescribe(control: HTMLElement): void {
  const ids = (control.getAttribute("aria-describedby") ?? "").split(" ").filter((id) => id && id !== TOOLTIP_ID);
  if (ids.length) control.setAttribute("aria-describedby", ids.join(" "));
  else control.removeAttribute("aria-describedby");
}

function place(node: HTMLElement, control: HTMLElement): void {
  const target = control.getBoundingClientRect();
  const box = node.getBoundingClientRect();
  const fitsBelow = target.bottom + GAP_PX + box.height <= window.innerHeight - EDGE_PX;
  const top = fitsBelow ? target.bottom + GAP_PX : target.top - GAP_PX - box.height;
  const maxLeft = window.innerWidth - box.width - EDGE_PX;
  const left = Math.max(EDGE_PX, Math.min(target.left, maxLeft));
  node.style.top = `${Math.max(EDGE_PX, top)}px`;
  node.style.left = `${left}px`;
}

function reveal(control: HTMLElement): void {
  if (!control.isConnected) {
    hide();
    return;
  }
  const node = tooltipNode();
  // A modal dialog sits in the top layer and would cover anything outside it.
  const host = control.closest("dialog") ?? document.body;
  if (node.parentElement !== host) host.append(node);
  node.hidden = false;
  place(node, control);
}

function hide(): void {
  clearTimeout(timer);
  if (current) undescribe(current);
  current = null;
  tooltipNode().hidden = true;
}

function start(control: HTMLElement): void {
  if (control === current) return;
  hide();
  current = control;
  fill(tooltipNode(), control);
  describe(control);
  timer = setTimeout(() => reveal(control), SHOW_DELAY_MS);
}

/** Find the control a pointer or focus event belongs to. */
function controlFor(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null;
  const tipped = node.closest<HTMLElement>("[data-tip]");
  if (tipped) return tipped;
  const control = node.closest("label")?.control;
  return control instanceof HTMLElement && control.dataset.tip ? control : null;
}

function onOver(event: Event): void {
  const control = controlFor(event.target);
  if (control) start(control);
  else hide();
}

function onOut(event: Event): void {
  const next = (event as MouseEvent).relatedTarget;
  if (controlFor(next) !== current) hide();
}

function onFocus(event: Event): void {
  const control = controlFor(event.target);
  if (control?.matches(":focus-visible")) start(control);
}

/**
 * Listen for the pointer and keyboard focus.
 *
 * Called once at startup, and again in tests after the markup changes.
 * The wizard bundle shares this page, so its controls are covered too.
 *
 * @param lookup Returns the keys for a shortcut id, or null when it has none.
 * @returns {void}
 */
export function wireTooltips(lookup: (id: string) => string | null): void {
  keysFor = lookup;
  hide();
  document.addEventListener("mouseover", onOver);
  document.addEventListener("mouseout", onOut);
  document.addEventListener("focusin", onFocus);
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", hide);
  document.addEventListener("pointerdown", hide);
  document.addEventListener("click", hide);
  document.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);
}
