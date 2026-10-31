/**
 * One tooltip for every control.
 *
 * Hover and keyboard focus show it. The control points at it with
 * aria-describedby while it is open, and that id is removed again on
 * blur so an existing description stays. Esc hides it and does not
 * cancel the key, so dialogs and search still receive Esc. A hover waits
 * briefly. prefers-reduced-motion shows it at once and the CSS does not
 * animate it. The node uses the Popover API when the browser has it, so
 * it sits above a modal dialog.
 */

import { hasKey, t } from "./i18n";
import { crateSortTip, sortTip, staticTip, viewTip, type TipSpec } from "./tooltip-strings";

/** Element id of the shared tooltip. */
export const TOOLTIP_ID = "app-tooltip";

/** Hover delay. Keyboard focus does not wait. Reduced motion waits 0. */
export const TOOLTIP_HOVER_MS = 400;

/**
 * Buttons, fields, sliders, tabs, menu items, and the other controls
 * the page paints. A control in this list with an empty data-tooltip
 * fails the audit.
 */
export const INTERACTIVE_SELECTOR = [
  "button",
  "input:not([type='hidden'])",
  "select",
  "textarea",
  "a[href]",
  "summary",
  "[role='slider']",
  "[role='button']",
  "[role='tab']",
  "[role='menuitem']",
  "[role='menuitemcheckbox']",
  "[role='menuitemradio']",
  "[role='switch']",
  "[role='option']",
  "[role='separator']",
  "[role='checkbox']",
  "[role='radio']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

let installed = false;
let current: HTMLElement | null = null;
let timer = 0;
let priorDescribedBy = "";
const tipParams = new WeakMap<HTMLElement, NonNullable<TipSpec["params"]>>();

function writeTooltip(element: HTMLElement): void {
  const key = element.dataset.tooltipKey ?? "";
  if (!hasKey(key)) throw new Error(`Unknown tooltip key ${key}.`);
  const value = t(key, tipParams.get(element)).trim();
  if (!value) throw new Error("A control tooltip cannot be empty.");
  element.dataset.tooltip = value;
}

function syncOpenTooltip(): void {
  if (!current) return;
  const tip = document.getElementById(TOOLTIP_ID);
  if (!(tip instanceof HTMLElement)) return;
  tip.textContent = current.dataset.tooltip ?? "";
}

/**
 * Put a tooltip sentence on a control.
 *
 * The sentence is `t(spec.key)`. The key stays on the element so a
 * language change can write it again. An empty sentence throws. A native
 * title is removed so the browser does not show a second tip.
 *
 * @param element Control that should describe itself.
 * @param spec Locale key and placeholder values.
 * @returns {void}
 */
export function setTooltip(element: HTMLElement, spec: TipSpec): void {
  element.dataset.tooltipKey = spec.key;
  if (spec.params) tipParams.set(element, spec.params);
  else tipParams.delete(element);
  writeTooltip(element);
  element.removeAttribute("title");
  if (current === element) syncOpenTooltip();
}

/**
 * Create a button that already has its tooltip.
 *
 * The type is button. A submit button sets type after this returns.
 *
 * @param spec Locale key and placeholder values.
 * @returns The button.
 */
export function buttonEl(spec: TipSpec): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  setTooltip(element, spec);
  return element;
}

/**
 * Create an input that already has its tooltip.
 *
 * The caller sets type when it is not text.
 *
 * @param spec Locale key and placeholder values.
 * @returns The input.
 */
export function inputEl(spec: TipSpec): HTMLInputElement {
  const element = document.createElement("input");
  setTooltip(element, spec);
  return element;
}

/**
 * Create a select that already has its tooltip.
 *
 * @param spec Locale key and placeholder values.
 * @returns The select.
 */
export function selectEl(spec: TipSpec): HTMLSelectElement {
  const element = document.createElement("select");
  setTooltip(element, spec);
  return element;
}

/**
 * Create a textarea that already has its tooltip.
 *
 * @param spec Locale key and placeholder values.
 * @returns The textarea.
 */
export function textareaEl(spec: TipSpec): HTMLTextAreaElement {
  const element = document.createElement("textarea");
  setTooltip(element, spec);
  return element;
}

/**
 * Copy tooltip sentences onto the controls that live in index.html.
 *
 * Ids, view tabs, column sort, and crate sort are covered. A control
 * with no sentence is left blank so the audit can see it. Safe to call
 * again after the markup is replaced.
 *
 * @param root Document or fragment that holds the page.
 * @returns {void}
 */
export function applyStaticTooltips(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>("[id]").forEach((node) => {
    const text = staticTip(node.id);
    if (text) setTooltip(node, text);
  });
  root.querySelectorAll<HTMLElement>("[data-view]").forEach((node) => {
    const text = viewTip(node.dataset.view ?? "");
    if (text) setTooltip(node, text);
  });
  root.querySelectorAll<HTMLElement>("[data-sort]").forEach((node) => {
    const label = node.textContent?.trim() || node.dataset.sort || "";
    setTooltip(node, sortTip(node.dataset.sort ?? "", label));
  });
  root.querySelectorAll<HTMLElement>("[data-crate-sort]").forEach((node) => {
    const text = crateSortTip(node.dataset.crateSort ?? "");
    if (text) setTooltip(node, text);
  });
}

/**
 * Write every attached tooltip again in the active language.
 *
 * Call this after the locale changes. Controls painted during the
 * repaint already call setTooltip. This covers the ones that stay on
 * the page, and the tooltip that is open.
 *
 * @param root Document or subtree to update.
 * @returns {void}
 */
export function refreshTooltips(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>("[data-tooltip-key]").forEach((node) => writeTooltip(node));
  if (current && !current.isConnected) {
    hide();
    return;
  }
  syncOpenTooltip();
}

/**
 * Listen for hover, focus, and Esc.
 *
 * Called once at startup. A second call does not add another listener.
 * Does not fetch.
 *
 * @returns {void}
 */
export function installTooltips(): void {
  if (installed) return;
  installed = true;
  document.addEventListener("pointerover", onPointerOver);
  document.addEventListener("pointerout", onPointerOut);
  document.addEventListener("focusin", onFocusIn);
  document.addEventListener("focusout", onFocusOut);
  document.addEventListener("keydown", onKeyDown);
  document.addEventListener("scroll", onScroll, true);
}

/**
 * Hide a tooltip left open by a previous test page.
 *
 * The listeners stay. The next show builds a new node if the body was
 * replaced.
 *
 * @returns {void}
 */
export function resetTooltipState(): void {
  window.clearTimeout(timer);
  timer = 0;
  if (current) restoreDescribedBy(current);
  current = null;
  const tip = document.getElementById(TOOLTIP_ID);
  if (tip instanceof HTMLElement) closeTip(tip);
}

/**
 * Controls in root whose tooltip sentence is missing.
 *
 * @param root Document or subtree to audit.
 * @returns Elements that match the interactive selector and have no sentence.
 */
export function controlsMissingTooltip(root: ParentNode = document): Element[] {
  return [...root.querySelectorAll(INTERACTIVE_SELECTOR)].filter((element) => {
    if (element.id === TOOLTIP_ID) return false;
    return (element.getAttribute("data-tooltip")?.trim() ?? "") === "";
  });
}

/**
 * Short labels for controls that failed the audit.
 *
 * @param root Document or subtree to audit.
 * @returns One line per control, with its id when it has one.
 */
export function missingTooltipLabels(root: ParentNode = document): string[] {
  return controlsMissingTooltip(root).map((element) => {
    const id = element.id ? `#${element.id}` : "";
    const label = element.getAttribute("aria-label") ?? "";
    const text = (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
    return `${element.tagName.toLowerCase()}${id} ${label} ${text}`.trim();
  });
}

function onPointerOver(event: PointerEvent): void {
  if (event.pointerType && event.pointerType !== "mouse") return;
  const target = tooltipTarget(event.target);
  if (!target) return;
  schedule(target, hoverDelay());
}

function onPointerOut(event: PointerEvent): void {
  if (event.pointerType && event.pointerType !== "mouse") return;
  const target = tooltipTarget(event.target);
  if (!target || tooltipTarget(event.relatedTarget) === target) return;
  if (current === target) hide();
}

function onFocusIn(event: FocusEvent): void {
  const target = tooltipTarget(event.target);
  if (!target) return;
  schedule(target, 0);
}

function onFocusOut(event: FocusEvent): void {
  if (tooltipTarget(event.relatedTarget)) return;
  const target = tooltipTarget(event.target);
  if (target && current === target) hide();
}

function onKeyDown(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !current) return;
  hide();
}

function onScroll(): void {
  if (current) hide();
}

function schedule(target: HTMLElement, delay: number): void {
  window.clearTimeout(timer);
  timer = 0;
  if (delay <= 0) {
    show(target);
    return;
  }
  timer = window.setTimeout(() => show(target), delay);
}

function show(target: HTMLElement): void {
  const text = target.dataset.tooltip?.trim() ?? "";
  if (!text) return;
  if (current && current !== target) restoreDescribedBy(current);
  current = target;
  const tip = ensureTip();
  tip.textContent = text;
  openTip(tip);
  place(target, tip);
  addDescribedBy(target);
}

function hide(): void {
  window.clearTimeout(timer);
  timer = 0;
  if (current) restoreDescribedBy(current);
  current = null;
  const tip = document.getElementById(TOOLTIP_ID);
  if (tip instanceof HTMLElement) closeTip(tip);
}

function hoverDelay(): number {
  if (typeof matchMedia !== "function") return TOOLTIP_HOVER_MS;
  return matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : TOOLTIP_HOVER_MS;
}

function tooltipTarget(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null;
  const direct = node.closest<HTMLElement>("[data-tooltip]");
  if (direct?.dataset.tooltip?.trim()) return direct;
  const label = node instanceof HTMLLabelElement ? node : node.closest("label");
  if (!(label instanceof HTMLLabelElement)) return null;
  if (label.control instanceof HTMLElement && label.control.dataset.tooltip?.trim()) return label.control;
  const nested = label.querySelector<HTMLElement>("[data-tooltip]");
  if (nested?.dataset.tooltip?.trim()) return nested;
  return null;
}

function ensureTip(): HTMLElement {
  const existing = document.getElementById(TOOLTIP_ID);
  if (existing instanceof HTMLElement) return existing;
  const tip = document.createElement("div");
  tip.id = TOOLTIP_ID;
  tip.className = "app-tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  tip.setAttribute("popover", "manual");
  document.body.append(tip);
  return tip;
}

function openTip(tip: HTMLElement): void {
  tip.hidden = false;
  if (typeof tip.showPopover !== "function") return;
  try {
    if (!tip.matches(":popover-open")) tip.showPopover();
  } catch {
    // jsdom and a browser without popover keep the node in normal flow.
  }
}

function closeTip(tip: HTMLElement): void {
  if (typeof tip.hidePopover === "function") {
    try {
      if (tip.matches(":popover-open")) tip.hidePopover();
    } catch {
      // Already closed.
    }
  }
  tip.hidden = true;
}

function place(target: HTMLElement, tip: HTMLElement): void {
  const rect = target.getBoundingClientRect();
  const gap = 8;
  const margin = 8;
  tip.style.position = "fixed";
  tip.style.margin = "0";
  tip.style.left = "0px";
  tip.style.top = "0px";
  const tipRect = tip.getBoundingClientRect();
  let top = rect.bottom + gap;
  let left = rect.left;
  if (top + tipRect.height > window.innerHeight - margin) top = Math.max(margin, rect.top - gap - tipRect.height);
  if (left + tipRect.width > window.innerWidth - margin) left = window.innerWidth - margin - tipRect.width;
  tip.style.left = `${Math.round(Math.max(margin, left))}px`;
  tip.style.top = `${Math.round(Math.max(margin, top))}px`;
}

function addDescribedBy(target: HTMLElement): void {
  if (target.dataset.tooltipLive === "1") return;
  target.dataset.tooltipLive = "1";
  priorDescribedBy = target.getAttribute("aria-describedby") ?? "";
  const ids = priorDescribedBy.split(/\s+/).filter((id) => id.length > 0 && id !== TOOLTIP_ID);
  ids.push(TOOLTIP_ID);
  target.setAttribute("aria-describedby", ids.join(" "));
}

function restoreDescribedBy(target: HTMLElement): void {
  if (target.dataset.tooltipLive !== "1") return;
  delete target.dataset.tooltipLive;
  if (priorDescribedBy) target.setAttribute("aria-describedby", priorDescribedBy);
  else target.removeAttribute("aria-describedby");
  priorDescribedBy = "";
}
