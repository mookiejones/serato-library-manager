import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GigReport } from "./api-types";
import { loadGigCheck, wireGigCheck } from "./gig";
import { state } from "./state";
import { installPage } from "./test-page";

const report: GigReport = {
  ready: false,
  score: 72,
  hard_red: true,
  holding_it_back: [{ code: "missing_files", points: 8, hard_red: true, summary: "1 missing file." }],
  missing_files: [{ path: "/Music/gone.mp3", title: "Gone", artist: "A", crate: "Friday" }],
  unavailable_drives: [{ name: "GIGDRIVE", track_count: 2, crates: ["Friday"] }],
  streaming_tracks: [{ service: "Apple Music", path: "stream", title: "Cloud", artist: "A", crate: "Friday" }],
  empty_crates: [{ name: "Late", warning: "Serato may delete this crate when it closes." }],
  snapshot_note: "Latest snapshot: Before Friday on 2026-10-27.",
  changes: {
    crates_added: ["Saturday"],
    crates_removed: [],
    crates_edited: [],
    tracks_added: [],
    tracks_removed: [],
    cues_edited: ["/Music/opener.mp3"],
    grids_edited: [],
    tags_edited: [],
  },
  scope: { space: "Serato Library", crate_id: 5, crate_name: "Friday" },
};

const clear: GigReport = {
  ready: true,
  score: 100,
  hard_red: false,
  holding_it_back: [],
  missing_files: [],
  unavailable_drives: [],
  streaming_tracks: [],
  empty_crates: [],
  snapshot_note: "",
  changes: {
    crates_added: [],
    crates_removed: [],
    crates_edited: [],
    tracks_added: [],
    tracks_removed: [],
    cues_edited: [],
    grids_edited: [],
    tags_edited: [],
  },
  scope: { space: "Serato Library", crate_id: null, crate_name: null },
};

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function reportText(): string {
  return document.getElementById("gig-report")!.textContent || "";
}

function clickAction(action: string): void {
  const button = document.querySelector<HTMLButtonElement>(`[data-gig-action="${action}"]`);
  if (!button) throw new Error(`missing ${action}`);
  button.click();
}

describe("gig", () => {
  beforeEach(() => {
    installPage();
    state.space = "Serato Library";
    state.activeCrate = 5;
    state.gigToken = 0;
    state.crates = [{ id: 5, name: "Friday" }];
    wireGigCheck(() => {
      state.mode = "crates";
    });
    document.getElementById("gig-panel")!.hidden = false;
  });

  it("asks for the selected crate and paints the verdict, missing files, and changes", async () => {
    const fetchMock = vi.fn(async () => reply(report));
    vi.stubGlobal("fetch", fetchMock);
    await loadGigCheck();
    expect(fetchMock).toHaveBeenCalledWith("/api/gig-check?space=Serato%20Library&crate=5");
    const score = document.querySelector(".gig-score")!;
    expect(score.getAttribute("aria-label")).toBe("Ready score 72 out of 100, not ready");
    expect(score.textContent).toContain("72/100");
    expect(score.textContent).toContain("✕ Not ready");
    expect(reportText()).toContain("Step 1 of 5");
    expect(reportText()).toContain("GIGDRIVE");
    clickAction("next");
    expect(reportText()).toContain("Step 2 of 5");
    expect(reportText()).toContain("/Music/gone.mp3");
    expect(reportText()).toContain("Locate missing files");
    clickAction("next");
    clickAction("next");
    clickAction("next");
    expect(reportText()).toContain("Step 5 of 5");
    expect(reportText()).toContain("Crates added");
    expect(reportText()).toContain("Saturday");
    expect(reportText()).toContain("Cues edited");
    expect(reportText()).not.toContain("Tags edited");
    expect(document.getElementById("gig-scope")!.textContent).toContain("Friday");
    expect(document.getElementById("gig-scope")!.textContent).not.toContain("Nothing is written");
    expect(document.getElementById("gig-refresh")!.getAttribute("aria-busy")).toBe("false");
    expect(document.getElementById("gig-refresh")!.hasAttribute("disabled")).toBe(false);
  });

  it("ignores a late reply after a newer check started", async () => {
    let finish: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const first = loadGigCheck();
    const firstFinish = finish;
    const second = loadGigCheck();
    finish(reply({ ...report, ready: true, score: 100, holding_it_back: [], unavailable_drives: [] }));
    await second;
    firstFinish(reply(report));
    await first;
    expect(document.querySelector(".gig-score")!.getAttribute("aria-label")).toBe("Ready score 100 out of 100, ready");
    expect(document.querySelector(".gig-score")!.textContent).toContain("✓ Ready");
    expect(document.querySelector(".gig-score")!.textContent).not.toContain("Not ready");
  });

  it("shows a server error in the status line and leaves the report", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ error: "That crate is not in this space." }, 404)));
    await loadGigCheck();
    expect(document.getElementById("gig-status")!.textContent).toBe("That crate is not in this space.");
    expect(document.activeElement?.id).toBe("gig-refresh");
  });

  it("checks again without clearing the report, and focuses retry when the server is unreachable", async () => {
    const second = new Promise<Response>((_resolve, reject) => {
      reject(new TypeError("Failed to fetch"));
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply(report))
      .mockImplementationOnce(() => second);
    vi.stubGlobal("fetch", fetchMock);
    await loadGigCheck();
    expect(reportText()).toContain("GIGDRIVE");
    const refresh = document.getElementById("gig-refresh") as HTMLButtonElement;
    refresh.click();
    expect(refresh.disabled).toBe(true);
    expect(document.getElementById("gig-refresh")!.getAttribute("aria-busy")).toBe("true");
    expect(reportText()).toContain("GIGDRIVE");
    await vi.waitFor(() => {
      expect(document.getElementById("gig-status")!.textContent).toBe(
        "Couldn't reach the library server. Check it's running, then press Check again",
      );
    });
    expect(reportText()).toContain("GIGDRIVE");
    expect(document.activeElement?.id).toBe("gig-refresh");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("puts a long list in a details group and can show every row", async () => {
    const missing = Array.from({ length: 101 }, (_, index) => ({
      path: `/Music/${index}.mp3`,
      title: "T",
      artist: "A",
      crate: "Friday",
    }));
    vi.stubGlobal("fetch", vi.fn(async () => reply({ ...report, missing_files: missing, unavailable_drives: [] })));
    await loadGigCheck();
    clickAction("next");
    const group = document.querySelector("details.gig-group")!;
    expect(group.querySelector("summary")!.textContent).toBe("Missing files (101)");
    expect(group.querySelectorAll("li")).toHaveLength(100);
    const show = group.querySelector("button")!;
    expect(show.textContent).toBe("Show all 101");
    show.click();
    expect(group.querySelectorAll("li")).toHaveLength(101);
    expect(group.querySelector("button")).toBeNull();
  });

  it("says when a step has nothing to fix", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(clear)));
    await loadGigCheck();
    expect(reportText()).toContain("No drives are unplugged.");
    expect(document.querySelector(".gig-score")!.textContent).toContain("✓ Ready");
    clickAction("next");
    clickAction("next");
    clickAction("next");
    clickAction("next");
    expect(reportText()).toContain("Nothing changed since the last snapshot.");
    expect(reportText()).not.toContain("Latest snapshot");
    const notes = [...document.querySelectorAll(".gig-note")].map((node) => node.textContent);
    expect(notes.every((text) => text && text.trim().length > 0)).toBe(true);
  });

  it("walks the five steps, focuses each heading, and ends on the done screen", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(clear)));
    let left = false;
    wireGigCheck(() => {
      left = true;
    });
    await loadGigCheck();
    const panel = document.getElementById("gig-panel")!;
    expect(panel.getAttribute("role")).toBe("tabpanel");
    expect(document.getElementById("gig-tab")!.getAttribute("aria-controls")).toBe("gig-panel");
    expect(document.getElementById("gig-report")!.getAttribute("aria-live")).toBeNull();
    expect(document.getElementById("gig-status")!.getAttribute("aria-live")).toBe("polite");
    expect(document.activeElement?.id).toBe("gig-step-heading");
    const titles = ["Drives", "Missing files", "Streaming", "Empty crates", "Since last gig"];
    for (let index = 0; index < titles.length; index += 1) {
      expect(reportText()).toContain(`Step ${index + 1} of 5`);
      expect(document.getElementById("gig-step-heading")!.textContent).toBe(titles[index]);
      expect(document.activeElement?.id).toBe("gig-step-heading");
      clickAction("next");
    }
    expect(reportText()).not.toContain("Step 6 of 5");
    expect(document.getElementById("gig-step-heading")!.textContent).toBe("Done");
    expect(reportText()).toMatch(/Ready for the gig: 100\/100, checked the whole space at \d{1,2}:\d{2} [AP]M/);
    const art = document.getElementById("gig-ready-art")!;
    expect(art.dataset.slot).toBe("gig-ready");
    expect(art.childElementCount).toBe(0);
    clickAction("back");
    expect(reportText()).toContain("Step 5 of 5");
    clickAction("exit");
    expect(left).toBe(true);
  });
});
