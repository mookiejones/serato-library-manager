/**
 * A draggable divider between a list pane and a details pane.
 *
 * The handle is a focusable `role="separator"` placed between the two
 * panes. It writes the first pane's width into a CSS custom property on
 * the container, and the stylesheet reads that property. Drag, arrow
 * keys, Home, and End move it. A double-click clears the property so the
 * stylesheet's default split returns. No request is made here. The
 * caller saves the width from onCommit.
 */

export interface SplitterOptions {
  /** The `role="separator"` element between the panes. */
  handle: HTMLElement;
  /** The grid that holds both panes and the handle. */
  container: HTMLElement;
  /** The pane on the left, whose width the handle sets. */
  first: HTMLElement;
  /** Custom property on the container, such as `--track-list-width`. */
  property: string;
  /** Narrowest the first pane may be, in CSS pixels. */
  minFirst: number;
  /** Narrowest the second pane may be, in CSS pixels. */
  minSecond: number;
  /** Arrow-key step in pixels. Shift multiplies it by four. */
  step?: number;
  /** Called after a drag ends, a key moves it, or a reset. Null is the default split. */
  onCommit: (width: number | null) => void;
}

export interface Splitter {
  /** Apply a saved width, or null for the default split. Does not call onCommit. */
  set(width: number | null): void;
  /** The width set by the person or by set(). Null is the default split. */
  width(): number | null;
  /** Redraw after the container changed size. Keeps the chosen width. Does not call onCommit. */
  refit(): void;
}

/**
 * Keep the first pane inside the room the container has.
 *
 * @param width Wanted first-pane width in pixels.
 * @param available Container width minus the handle, in pixels.
 * @param minFirst Narrowest first pane.
 * @param minSecond Narrowest second pane.
 * @returns A whole-pixel width. When the container is too narrow for both
 *   minimums, the first pane keeps its minimum.
 */
export function clampWidth(width: number, available: number, minFirst: number, minSecond: number): number {
  const max = Math.max(minFirst, available - minSecond);
  return Math.round(Math.min(Math.max(width, minFirst), max));
}

/**
 * Attach drag, keyboard, and double-click handling to a separator.
 *
 * @param options Elements, limits, and the commit callback.
 * @returns A handle for applying a saved width and refitting on resize.
 */
export function mountSplitter(options: SplitterOptions): Splitter {
  const { handle, container, first, property, minFirst, minSecond, onCommit } = options;
  const step = options.step ?? 16;
  let current: number | null = null;

  const available = (): number => container.clientWidth - handle.offsetWidth;
  const fitted = (width: number): number => clampWidth(width, available(), minFirst, minSecond);
  const shown = (): number => (current == null ? first.getBoundingClientRect().width : fitted(current));

  // current is the width the person chose. paint() draws it clamped to the
  // room there is now, so a narrower window does not overwrite the choice.
  function paint(): void {
    if (current == null) container.style.removeProperty(property);
    else container.style.setProperty(property, `${fitted(current)}px`);
    const room = available();
    handle.setAttribute("aria-valuemin", String(minFirst));
    handle.setAttribute("aria-valuemax", String(Math.max(minFirst, Math.round(room - minSecond))));
    handle.setAttribute("aria-valuenow", String(Math.round(shown())));
  }

  function move(width: number): void {
    current = fitted(width);
    paint();
  }

  handle.addEventListener("pointerdown", (event: PointerEvent) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = shown();
    let moved = false;
    handle.setPointerCapture?.(event.pointerId);
    handle.dataset.dragging = "true";
    document.body.classList.add("is-resizing");
    const onMove = (next: PointerEvent): void => {
      moved = true;
      move(startWidth + next.clientX - startX);
    };
    const onEnd = (): void => {
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onEnd);
      handle.removeEventListener("pointercancel", onEnd);
      delete handle.dataset.dragging;
      document.body.classList.remove("is-resizing");
      if (moved) onCommit(current);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onEnd);
    handle.addEventListener("pointercancel", onEnd);
  });

  handle.addEventListener("keydown", (event: KeyboardEvent) => {
    const jump = event.shiftKey ? step * 4 : step;
    let next: number;
    if (event.key === "ArrowLeft") next = shown() - jump;
    else if (event.key === "ArrowRight") next = shown() + jump;
    else if (event.key === "Home") next = minFirst;
    else if (event.key === "End") next = available() - minSecond;
    else return;
    event.preventDefault();
    const before = current;
    move(next);
    if (current !== before) onCommit(current);
  });

  handle.addEventListener("dblclick", () => {
    current = null;
    paint();
    onCommit(null);
  });

  paint();
  return {
    set(width) {
      current = width == null ? null : Math.round(width);
      paint();
    },
    width: () => current,
    refit: paint,
  };
}
