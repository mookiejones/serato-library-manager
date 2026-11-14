/**
 * MUI Alert for the global action-flash notice.
 */

import { createElement } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NoticeProvider } from "../../containers/NoticeContext";
import { NoticeBanner } from "../../components/NoticeBanner";
import { t } from "../../lib/i18n";
import { installPage } from "../test-page";

describe("NoticeBanner", () => {
  let host: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    installPage();
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(() => {
    flushSync(() => {
      root.unmount();
    });
    host.remove();
  });

  it("renders nothing when there is no notice", () => {
    flushSync(() => {
      root.render(
        createElement(NoticeProvider, {
          value: { notice: null, dismiss: vi.fn() },
          children: createElement(NoticeBanner),
        }),
      );
    });
    expect(host.querySelector("#app-notice")).toBeNull();
  });

  it("shows an error Alert with role alert", () => {
    flushSync(() => {
      root.render(
        createElement(NoticeProvider, {
          value: {
            notice: { text: "That file is not on disk.", severity: "error" },
            dismiss: vi.fn(),
          },
          children: createElement(NoticeBanner),
        }),
      );
    });
    const snackbar = document.querySelector(".MuiSnackbar-root");
    const banner = document.getElementById("app-notice");
    expect(snackbar).not.toBeNull();
    expect(snackbar?.contains(banner)).toBe(true);
    expect(banner?.textContent).toContain("That file is not on disk.");
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(banner?.className).toContain("MuiAlert-colorError");
  });

  it("shows an info Alert with role status", () => {
    flushSync(() => {
      root.render(
        createElement(NoticeProvider, {
          value: {
            notice: { text: "Saved.", severity: "info" },
            dismiss: vi.fn(),
          },
          children: createElement(NoticeBanner),
        }),
      );
    });
    const banner = host.querySelector("#app-notice");
    expect(banner?.getAttribute("role")).toBe("status");
    expect(banner?.className).toContain("MuiAlert-colorInfo");
  });

  it("dismisses from the close button", () => {
    const dismiss = vi.fn();
    flushSync(() => {
      root.render(
        createElement(NoticeProvider, {
          value: {
            notice: { text: "Saved.", severity: "success" },
            dismiss,
          },
          children: createElement(NoticeBanner),
        }),
      );
    });
    const close = host.querySelector<HTMLButtonElement>("#app-notice button");
    expect(close?.getAttribute("aria-label")).toBe(t("common.close"));
    close?.click();
    expect(dismiss).toHaveBeenCalledTimes(1);
  });
});
