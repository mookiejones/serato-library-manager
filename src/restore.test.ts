import { beforeEach, describe, expect, it, vi } from "vitest";

const postJSON = vi.hoisted(() => vi.fn());

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, postJSON };
});

import { setLocale } from "./i18n";
import { confirmSnapshotRestore, openSnapshotPlan, renderSnapshots, repaintSnapshotPlan } from "./restore";
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

  it("translates an unknown Serato version on the snapshot note and the plan", async () => {
    state.snapshotLoading = false;
    state.snapshotError = "";
    state.snapshots = [];
    state.writeBlock = "Serato version is unknown (build 9.9).";
    state.writeBlockCode = "serato_version_unknown";
    state.writeBlockParams = { build: "9.9" };
    renderSnapshots();
    expect(document.getElementById("snapshots-block")?.textContent).toContain("build 9.9");
    setLocale("es");
    renderSnapshots();
    expect(document.getElementById("snapshots-block")?.textContent).toContain("compilación 9.9");

    postJSON.mockResolvedValue({
      ...plan,
      restore_blocked: "Serato version is unknown (build 9.9).",
      restore_blocked_code: "serato_version_unknown",
      restore_blocked_params: { build: "9.9" },
    });
    await openSnapshotPlan("snap-9");
    expect(document.getElementById("snapshot-block")?.textContent).toContain("compilación 9.9");
    expect((document.getElementById("snapshot-confirm") as HTMLButtonElement).disabled).toBe(true);
    setLocale("en");
    repaintSnapshotPlan();
    expect(document.getElementById("snapshot-block")?.textContent).toContain("build 9.9");
  });

  it("repaints the open plan and the list message in Spanish", async () => {
    const many = { ...plan, crates: { ...plan.crates, added: Array.from({ length: 10 }, (_, index) => ({ name: `C${index}` })) } };
    postJSON.mockResolvedValue(many);
    await openSnapshotPlan("snap-9");
    let text = document.getElementById("snapshot-plan")?.textContent ?? "";
    expect(text).toContain("Crates added: 10. C0, C1, C2, C3, C4, C5, C6, C7, and 2 more");
    setLocale("es");
    try {
      repaintSnapshotPlan();
      text = document.getElementById("snapshot-plan")?.textContent ?? "";
      expect(text).toContain("Cajas añadidas: 10. C0, C1, C2, C3, C4, C5, C6, C7 y 2 más");
      expect(text).toContain("Cambios de cues: 1 archivo");
      expect(text).toContain("Pistas eliminadas: ninguno");
      expect(document.getElementById("snapshot-block")?.textContent).toBe("No se ha cambiado nada.");
      state.snapshotMessage = "snapshots.saved";
      state.snapshotLoading = false;
      state.snapshotError = "";
      state.snapshots = [];
      renderSnapshots();
      expect(document.getElementById("snapshots-status")?.textContent).toBe("Instantánea guardada.");
    } finally {
      setLocale("en");
    }
  });

  it("does not repaint a closed plan dialog", async () => {
    postJSON.mockResolvedValue(plan);
    await openSnapshotPlan("snap-9");
    (document.getElementById("snapshot-dialog") as HTMLDialogElement).close();
    document.getElementById("snapshot-plan")!.replaceChildren();
    repaintSnapshotPlan();
    expect(document.getElementById("snapshot-plan")?.textContent).toBe("");
  });
});
