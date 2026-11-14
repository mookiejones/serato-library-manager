/**
 * AppShell portals existing ids into AppBar, Drawer, and Main.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { flushSync } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "../../lib/api-types";
import { applyStatic, setLocale, t } from "../../lib/i18n";
import {
  attachMedia,
  getPlayerState,
  mountPlayer,
  pause,
  play,
  type PlayableMedia,
} from "../../lib/player/player";
import { state } from "../../lib/state";
import { applyLayout, DRAWER_MINI_CUTOFF } from "../../lib/ui/layout";
import { mountAppShell, unmountAppShell } from "../../lib/ui/app-shell";
import { paintNav, resetNav } from "../../lib/ui/nav";
import { resetNotice, setNotice } from "../../lib/ui/notice-store";
import { applyStatus } from "../../lib/ui/views";
import { applyStaticTooltips } from "../../lib/ui/tooltip";
import { installPage } from "../test-page";

const appCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../../static/app.css"),
  "utf8",
);

class FakeAudio extends EventTarget implements PlayableMedia {
  src = "";
  currentTime = 0;
  duration = 0;
  volume = 1;
  paused = true;
  play(): Promise<void> {
    this.paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  }
  pause(): void {
    this.paused = true;
    this.dispatchEvent(new Event("pause"));
  }
}

function sampleTrack(id: number, name: string, artist = "Ada"): Track {
  return { id, name, artist };
}

function playerSlotHidden(bar: HTMLElement | null): boolean {
  if (!bar) return true;
  const slot = bar.parentElement;
  if (!(slot instanceof HTMLElement)) return bar.hidden;
  return (
    bar.hidden
    || slot.hidden
    || slot.style.display === "none"
    || getComputedStyle(slot).display === "none"
  );
}

function remountShell(): void {
  unmountAppShell();
  installPage();
  mountAppShell();
}

function setInnerWidth(width: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
}

function drawerPaper(): HTMLElement {
  const paper = document.querySelector(".MuiDrawer-paper");
  if (!(paper instanceof HTMLElement)) {
    throw new Error("drawer paper missing");
  }
  return paper;
}

function layoutBodies(fetchMock: ReturnType<typeof vi.fn>): unknown[] {
  return fetchMock.mock.calls
    .filter((call) => call[0] === "/api/settings")
    .map((call) => {
      const init = call[1] as RequestInit | undefined;
      return JSON.parse(String(init?.body ?? "{}")) as unknown;
    });
}

describe("AppShell", () => {
  beforeEach(() => {
    installPage();
    setLocale("en");
    applyStatic(document);
    resetNav();
    mountAppShell();
    applyStaticTooltips();
  });

  afterEach(() => {
    unmountAppShell();
    resetNav();
    resetNotice();
    setLocale("en");
    vi.unstubAllGlobals();
  });

  it("portals primaries and children into the drawer, crates stay in Main", () => {
    const drawer = document.getElementById("app-drawer");
    const views = document.getElementById("views");
    const children = document.getElementById("view-children");
    const help = document.getElementById("open-help");
    const settings = document.getElementById("open-settings");
    const crates = document.getElementById("crate-list");
    const space = document.getElementById("space");
    const heading = document.querySelector("h1");
    const generation = document.getElementById("library-generation");
    const appBar = document.querySelector(".MuiAppBar-root");
    expect(drawer).not.toBeNull();
    expect(drawer?.contains(views)).toBe(true);
    expect(drawer?.contains(children)).toBe(true);
    expect(drawer?.contains(help)).toBe(false);
    expect(drawer?.contains(settings)).toBe(false);
    expect(drawer?.contains(crates)).toBe(false);
    expect(document.querySelector(".rail")?.contains(crates)).toBe(true);
    expect(document.getElementById("sheet-title")).not.toBeNull();
    expect(space?.tagName).toBe("SELECT");
    expect(appBar?.contains(space)).toBe(false);
    expect(document.querySelector(".brand")?.contains(space)).toBe(true);
    expect(document.querySelector(".brand")?.contains(heading)).toBe(false);
    expect(appBar?.contains(help)).toBe(true);
    expect(appBar?.contains(settings)).toBe(true);
    expect(appBar?.contains(heading)).toBe(true);
    expect(heading?.textContent).toBe("crateCraft");
    expect(appBar?.contains(generation)).toBe(true);
    expect(document.getElementById("track-splitter")?.getAttribute("role")).toBe("separator");
  });

  it("puts Skip to content first and points it at Main", () => {
    applyStatic(document);
    const skip = document.getElementById("skip-to-content");
    const first = document.body.querySelector("a, button, input, select, textarea");
    expect(skip).toBe(first);
    expect(skip?.getAttribute("href")).toBe("#app-body");
    expect(skip?.textContent).toBe("Skip to content");
    expect(document.getElementById("app-body")?.getAttribute("tabindex")).toBe("-1");
    expect(skip?.dataset.tooltip?.trim().length).toBeGreaterThan(10);
    setLocale("es");
    applyStatic(document);
    expect(document.getElementById("skip-to-content")?.textContent).toBe("Saltar al contenido");
  });

  it("collapse keeps Help in the AppBar and crate names in the rail", () => {
    const toggle = document.getElementById("drawer-toggle");
    const help = document.getElementById("open-help");
    const crates = document.getElementById("crate-list");
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    expect(toggle?.getAttribute("aria-label")).toBe(t("shell.drawerHide"));
    expect(help?.closest("[inert]")).toBeNull();
    flushSync(() => {
      toggle?.click();
    });
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(toggle?.getAttribute("aria-label")).toBe(t("shell.drawerShow"));
    expect(help?.closest("[inert]")).toBeNull();
    expect(document.querySelector(".MuiAppBar-root")?.contains(help)).toBe(true);
    expect(crates?.isConnected).toBe(true);
    expect(document.querySelector(".rail")?.contains(crates)).toBe(true);
    expect(document.getElementById("app-drawer")?.contains(crates)).toBe(false);
  });

  it("gives the drawer toggle a tooltip", () => {
    const toggle = document.getElementById("drawer-toggle");
    expect(toggle?.dataset.tooltip?.trim().length).toBeGreaterThan(10);
  });

  it("starts collapsed on a narrow screen and can open navigation", () => {
    const originalWidth = window.innerWidth;
    try {
      unmountAppShell();
      installPage();
      Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
      mountAppShell();
      const toggle = document.getElementById("drawer-toggle");
      expect(toggle?.getAttribute("aria-expanded")).toBe("false");
      expect(document.getElementById("open-help")?.closest("[inert]")).toBeNull();
      flushSync(() => { toggle?.click(); });
      expect(toggle?.getAttribute("aria-expanded")).toBe("false");
      expect(document.getElementById("views")?.closest("[inert]")).toBeNull();
      expect(document.getElementById("open-help")?.closest("[inert]")).toBeNull();
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
    }
  });

  it("docks the compact player in the AppBar after a track loads", () => {
    attachMedia(new FakeAudio());
    mountPlayer();
    const bar = document.getElementById("player-bar");
    const appBar = document.querySelector(".MuiAppBar-root");
    expect(bar).not.toBeNull();
    expect(appBar?.contains(bar)).toBe(true);
    expect(appBar?.nextElementSibling?.contains(bar)).toBe(false);
    expect(document.getElementById("app-body")?.contains(bar)).toBe(false);
    expect(getPlayerState().trackId).toBeNull();
    expect(playerSlotHidden(bar)).toBe(true);

    const night = sampleTrack(4, "Night");
    state.byId.set(4, night);
    flushSync(() => {
      play(4);
    });
    expect(playerSlotHidden(bar)).toBe(false);
    expect(bar?.querySelector(".player-play")).not.toBeNull();
    expect(bar?.querySelector(".player-title")?.textContent).toBe("Night");
    expect(bar?.querySelector("canvas")).not.toBeNull();
    expect(bar?.querySelector(".player-time")).not.toBeNull();
    expect(bar?.querySelector("[aria-label='Zoom in']")).toBeNull();
    expect(bar?.querySelector("[aria-label='Zoom out']")).toBeNull();

    flushSync(() => {
      pause();
    });
    expect(getPlayerState().playing).toBe(false);
    expect(getPlayerState().trackId).toBe(4);
    expect(playerSlotHidden(bar)).toBe(false);

    flushSync(() => {
      mountPlayer();
    });
    expect(getPlayerState().trackId).toBeNull();
    expect(playerSlotHidden(document.getElementById("player-bar"))).toBe(true);
  });

  it("keeps Help on the AppBar right while the player is hidden", () => {
    const bar = document.getElementById("player-bar");
    const actions = document.querySelector(".app-bar-actions");
    const help = document.getElementById("open-help");
    const settings = document.getElementById("open-settings");
    expect(playerSlotHidden(bar)).toBe(true);
    expect(actions).toBeInstanceOf(HTMLElement);
    expect(actions?.contains(help)).toBe(true);
    expect(actions?.contains(settings)).toBe(true);
    expect(getComputedStyle(actions as HTMLElement).marginLeft).toBe("auto");
  });

  it("shows the Serato lock copy under the AppBar without changing the chip", () => {
    const status = document.getElementById("status");
    const chip = document.getElementById("library-generation");
    const appBar = document.querySelector(".MuiAppBar-root");
    expect(status).not.toBeNull();
    expect(status?.hidden).toBe(true);
    expect(appBar?.contains(status)).toBe(false);
    expect(appBar?.nextElementSibling?.contains(status)).toBe(true);
    expect(document.querySelector(".brand")?.contains(status)).toBe(false);
    expect(chip?.textContent).not.toBe("Serato is open. Changes are paused.");

    flushSync(() => {
      applyStatus({
        writable: false,
        message: "Serato is open. Changes are paused.",
        generation: { kind: "serato4" },
      });
    });
    expect(status?.hidden).toBe(false);
    expect(status?.textContent).toBe("Serato is open. Changes are paused.");
    expect(appBar?.nextElementSibling?.contains(status)).toBe(true);
    expect(chip?.textContent).toBe(t("generation.serato4"));
    expect(appBar?.contains(document.getElementById("open-help"))).toBe(true);
    expect(document.getElementById("app-notice")).toBeNull();

    flushSync(() => {
      applyStatus({
        writable: true,
        generation: { kind: "serato4" },
      });
    });
    expect(status?.hidden).toBe(true);
    expect(chip?.textContent).toBe(t("generation.serato4"));

    flushSync(() => {
      setNotice("That file is not on disk.", "error");
    });
    const banner = document.getElementById("app-notice");
    expect(banner?.textContent).toContain("That file is not on disk.");
    expect(document.querySelector(".MuiSnackbar-root")?.contains(banner)).toBe(true);
    expect(document.getElementById("app-body")?.contains(banner)).toBe(false);
  });

  it("places a dismissible Alert under the AppBar for setNotice", () => {
    expect(document.getElementById("app-notice")).toBeNull();
    flushSync(() => {
      setNotice("That file is not on disk.", "error");
    });
    const banner = document.getElementById("app-notice");
    const snackbar = document.querySelector(".MuiSnackbar-root");
    const appBar = document.querySelector(".MuiAppBar-root");
    expect(banner?.textContent).toContain("That file is not on disk.");
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(snackbar).not.toBeNull();
    expect(snackbar?.contains(banner)).toBe(true);
    expect(appBar?.contains(banner)).toBe(false);
    expect(document.getElementById("app-body")?.contains(banner)).toBe(false);
    document.querySelector<HTMLButtonElement>("#app-notice button")?.click();
    expect(document.getElementById("app-notice")).toBeNull();
  });

  it("keeps Help in the AppBar while Settings fills Main", () => {
    const help = document.getElementById("open-help");
    const dialog = document.getElementById("settings-dialog");
    expect(dialog).not.toBeNull();
    if (dialog instanceof HTMLDialogElement && typeof dialog.show === "function") {
      dialog.show();
    }
    expect(document.querySelector(".MuiAppBar-root")?.contains(help)).toBe(true);
    expect(help?.closest("[inert]")).toBeNull();
    expect(document.getElementById("app-body")?.contains(dialog)).toBe(true);
  });

  it("opens the 200px drawer on a wide first launch", () => {
    setInnerWidth(1120);
    remountShell();
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("true");
    expect(drawerPaper().style.width || getComputedStyle(drawerPaper()).width).toBe("200px");
    expect(document.querySelector(".rail")?.contains(document.getElementById("crate-list"))).toBe(true);
    expect(document.getElementById("app-drawer")?.contains(document.getElementById("crate-list"))).toBe(false);
  });

  it("uses a mini drawer at 980px and keeps crate names in Main", () => {
    setInnerWidth(DRAWER_MINI_CUTOFF);
    remountShell();
    expect(DRAWER_MINI_CUTOFF).toBe(980);
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("false");
    expect(drawerPaper().style.width || getComputedStyle(drawerPaper()).width).toBe("56px");
    expect(document.querySelector(".rail")?.contains(document.getElementById("crate-list"))).toBe(true);
    expect(document.getElementById("app-drawer")?.contains(document.getElementById("crate-list"))).toBe(false);
  });

  it("uses a 56px mini drawer on a narrow first launch without inert", () => {
    setInnerWidth(390);
    remountShell();
    const views = document.getElementById("views");
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("app-drawer")?.contains(views)).toBe(true);
    expect(views?.closest("[inert]")).toBeNull();
    expect(document.querySelector(".MuiAppBar-root")?.contains(document.getElementById("open-help"))).toBe(true);
    expect(drawerPaper().style.width || getComputedStyle(drawerPaper()).width).toBe("56px");
  });

  it("starts mini when settings saved the drawer closed on a wide window", () => {
    setInnerWidth(1200);
    remountShell();
    flushSync(() => {
      applyLayout({ layout: { track_list_width: null, drawer_open: false } });
    });
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("views")?.closest("[inert]")).toBeNull();
    expect(drawerPaper().style.width || getComputedStyle(drawerPaper()).width).toBe("56px");
  });

  it("goes mini on a narrow resize without posting drawer_open false", () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setInnerWidth(1200);
    remountShell();
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("true");
    setInnerWidth(500);
    flushSync(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("false");
    expect(500).toBeLessThan(DRAWER_MINI_CUTOFF);
    expect(layoutBodies(fetchMock).some((body) => {
      const layout = (body as { layout?: { drawer_open?: boolean } }).layout;
      return layout?.drawer_open === false;
    })).toBe(false);
  });

  it("posts drawer_open when the toggle is clicked", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setInnerWidth(1200);
    remountShell();
    const toggle = document.getElementById("drawer-toggle");
    flushSync(() => {
      toggle?.click();
    });
    await vi.waitFor(() => {
      expect(layoutBodies(fetchMock)).toContainEqual({ layout: { drawer_open: false } });
    });
    flushSync(() => {
      toggle?.click();
    });
    await vi.waitFor(() => {
      expect(layoutBodies(fetchMock)).toContainEqual({ layout: { drawer_open: true } });
    });
  });

  it("still paints only the open parent's children after the portal", () => {
    paintNav("crates");
    const visible = [...document.querySelectorAll<HTMLButtonElement>("#view-children [data-view]")]
      .filter((button) => !button.hidden)
      .map((button) => button.dataset.view);
    expect(document.getElementById("view-children")?.hidden).toBe(false);
    expect(visible).toEqual(["crates", "history", "stats"]);
    paintNav("files");
    expect(document.getElementById("view-children")?.hidden).toBe(true);
  });

  it("nests Music children under the Music button inside #views", () => {
    paintNav("crates");
    const strip = document.getElementById("view-children");
    const views = document.getElementById("views");
    const music = document.querySelector('[data-nav="library"]');
    expect(views?.contains(strip)).toBe(true);
    expect(music?.nextElementSibling).toBe(strip);
    expect(document.querySelector("main.sheet")?.contains(strip)).toBe(false);
    const visible = [...document.querySelectorAll<HTMLButtonElement>("#view-children [data-view]")]
      .filter((button) => !button.hidden)
      .map((button) => button.dataset.view);
    expect(visible).toEqual(["crates", "history", "stats"]);
  });

  it("hides the child strip on Organize files", () => {
    paintNav("files");
    const strip = document.getElementById("view-children");
    const files = document.querySelector('[data-nav="files"]');
    expect(strip?.hidden).toBe(true);
    expect(files?.querySelector("#view-children")).toBeNull();
  });

  it("hides nested children when the drawer is mini and keeps five primaries", () => {
    setInnerWidth(390);
    remountShell();
    paintNav("crates");
    const strip = document.getElementById("view-children");
    expect(document.getElementById("drawer-toggle")?.getAttribute("aria-expanded")).toBe("false");
    expect(strip?.hidden || getComputedStyle(strip!).display === "none").toBe(true);
    const primaries = [...document.querySelectorAll<HTMLButtonElement>("#views [data-nav]")];
    expect(primaries).toHaveLength(5);
    for (const button of primaries) {
      expect(button.hidden).toBe(false);
      expect(button.querySelector("svg")).not.toBeNull();
    }
  });

  it("mini drawer CSS fits a 24px icon in 56px without label gap", () => {
    const miniNav = appCss.match(/#app-drawer\[data-mini\] \.view-switch \[data-nav\] \{[^}]+\}/);
    expect(miniNav).not.toBeNull();
    expect(miniNav![0]).toMatch(/gap:\s*0/);
    expect(miniNav![0]).toMatch(/font-size:\s*0/);
    expect(miniNav![0]).toMatch(/padding-left:\s*16px/);
    expect(miniNav![0]).toMatch(/padding-right:\s*16px/);
  });
});
