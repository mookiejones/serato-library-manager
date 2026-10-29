import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GigReport } from "./api-types";
import { loadGigCheck, showGigFailure } from "./gig";
import { state } from "./state";
import { installPage } from "./test-page";

const report: GigReport = {
  ready: false,
  score: 72,
  hard_red: true,
  holding_it_back: [{ code: "missing_files", points: 8, hard_red: true, summary: "1 missing file." }],
  missing_files: [{ path: "/Music/gone.mp3", title: "Gone", artist: "A", crate: "Friday" }],
  unavailable_drives: [],
  streaming_tracks: [],
  empty_crates: [],
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

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("gig", () => {
  beforeEach(() => {
    installPage();
    state.space = "Serato Library";
    state.activeCrate = 5;
    state.gigToken = 0;
  });

  it("asks for the selected crate and paints the verdict, missing files, and changes", async () => {
    const fetchMock = vi.fn(async () => reply(report));
    vi.stubGlobal("fetch", fetchMock);
    await loadGigCheck();
    expect(fetchMock).toHaveBeenCalledWith("/api/gig-check?space=Serato%20Library&crate=5");
    const text = document.getElementById("gig-report")!.textContent || "";
    expect(text).toContain("Not ready");
    expect(text).toContain("72");
    expect(text).toContain("/Music/gone.mp3");
    expect(text).toContain("Crates added");
    expect(text).toContain("Saturday");
    expect(text).toContain("Cues edited");
    expect(text).not.toContain("Tags edited");
    expect(document.getElementById("gig-scope")!.textContent).toContain("Friday");
    expect(document.getElementById("gig-report")!.getAttribute("aria-busy")).toBe("false");
  });

  it("ignores a late reply after a newer check started", async () => {
    let finish: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const first = loadGigCheck();
    const firstFinish = finish;
    const second = loadGigCheck();
    finish(reply({ ...report, ready: true, score: 100, holding_it_back: [] }));
    await second;
    firstFinish(reply(report));
    await first;
    expect(document.getElementById("gig-report")!.textContent).toContain("Ready");
    expect(document.getElementById("gig-report")!.textContent).not.toContain("Not ready");
  });

  it("shows the server error in the report", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ error: "That crate is not in this space." }, 404)));
    await loadGigCheck().catch(showGigFailure);
    expect(document.getElementById("gig-report")!.textContent).toBe("That crate is not in this space.");
  });
});
