/**
 * Fuzzy scoring used by quick-open.
 *
 * A prefix beats a later copy of the same word. A sparse subsequence
 * still matches. A missing letter does not.
 */

import { describe, expect, it } from "vitest";
import { fuzzyScore, scoreQuery } from "./fuzzy";

describe("fuzzy score", () => {
  it("ranks a prefix above a later copy and still matches a subsequence", () => {
    const prefix = fuzzyScore("same", "same-a.mp3");
    const later = fuzzyScore("same", "zz-same.mp3");
    const sparse = fuzzyScore("hs", "House Mix.mp3");
    expect(prefix).not.toBeNull();
    expect(later).not.toBeNull();
    expect(sparse).not.toBeNull();
    expect(prefix!).toBeGreaterThan(later!);
    expect(fuzzyScore("zzz", "House Mix.mp3")).toBeNull();
    expect(fuzzyScore("SAME", "same-a.mp3")).toBe(prefix);
  });

  it("requires every word, and a folder name can supply one of them", () => {
    expect(scoreQuery("deep house", "House Mix.mp3", "Deep")).not.toBeNull();
    expect(scoreQuery("deep house", "House Mix.mp3")).toBeNull();
    expect(scoreQuery("   ", "House Mix.mp3")).toBeNull();
    expect(scoreQuery("house", "House Mix.mp3", "Deep")).not.toBeNull();
  });
});
