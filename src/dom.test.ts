import { beforeEach, describe, expect, it } from "vitest";
import { el } from "./dom";
import { installPage } from "./test-page";

describe("el", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("throws when the id is not in the page", () => {
    expect(() => el("search")).toThrow(/Missing #search/);
  });

  it("returns the element index.html ships", () => {
    installPage();
    const search = el("search");
    expect(search).toBeInstanceOf(HTMLInputElement);
    expect(search.id).toBe("search");
  });
});
