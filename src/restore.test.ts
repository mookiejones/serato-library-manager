import { beforeEach, describe, expect, it, vi } from "vitest";

const postJSON = vi.hoisted(() => vi.fn());

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, postJSON };
});

import { confirmSnapshotRestore, openSnapshotPlan } from "./restore";
import type { RestorePlan } from "./api-types";
import { state } from "./state";
import { installPage } from "./test-page";

const plan: RestorePlan = {
  crates: {
    added: [{ name: "House" }],
    removed: [],
    changed: [],
    unavailable: [],
  },
  tracks: {
    added: [{ path: "Music/a.mp3" }],
    removed: [],
    unavailable: [],
  },
  cues: [{ path: "Music/a.mp3" }],
  grids: [{ path: "Music/b.mp3" }],
  deleted: {
    crates: [{ name: "Old" }],
    tracks: [],
    cues: [],
    grids: [],
  },
  dry_run: true,
  restore_blocked: null,
};

function snapshotResponse(): Response {
  return new Response(JSON.stringify({
    snapshots: [],
    pending_undo: null,
    write_block: "",
    serato_running: false,
  }), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("restore", () => {
  beforeEach(() => {
    installPage();
    state.snapshotPlanId = "snap-9";
    state.snapshotUndo = null;
    state.snapshotMessage = "";
    postJSON.mockReset();
    postJSON.mockResolvedValue({});
    vi.stubGlobal("fetch", vi.fn(async () => snapshotResponse()));
  });

  it("posts undo or restore with confirm true", async () => {
    await confirmSnapshotRestore();
    expect(postJSON).toHaveBeenCalledWith("/api/snapshots", {
      action: "restore",
      id: "snap-9",
      confirm: true,
    });

    state.snapshotUndo = { restore_id: "snap-9" };
    state.snapshotPlanId = "snap-9";
    await confirmSnapshotRestore();
    expect(postJSON).toHaveBeenLastCalledWith("/api/snapshots", {
      action: "undo",
      confirm: true,
    });
  });

  it("paints the dry-run plan fields and blocks confirm when restore is refused", async () => {
    postJSON.mockResolvedValue(plan);
    await openSnapshotPlan("snap-9");
    const text = document.getElementById("snapshot-plan")?.textContent ?? "";
    expect(text).toContain("Crates added: 1. House");
    expect(text).toContain("Tracks added: 1. Music/a.mp3");
    expect(text).toContain("Cue changes: 1 file");
    expect(text).toContain("Grid changes: 1 file");
    expect(text).toContain("Deleted crates: 1. Old");
    expect(text).toContain("Deleted tracks: none");
    expect(document.getElementById("snapshot-block")?.textContent).toBe("Nothing has been changed.");
    expect((document.getElementById("snapshot-confirm") as HTMLButtonElement).disabled).toBe(false);

    postJSON.mockResolvedValue({ ...plan, restore_blocked: "Quit Serato before restoring." });
    await openSnapshotPlan("snap-9");
    expect(document.getElementById("snapshot-block")?.textContent).toBe("Quit Serato before restoring.");
    expect((document.getElementById("snapshot-confirm") as HTMLButtonElement).disabled).toBe(true);
  });
});
