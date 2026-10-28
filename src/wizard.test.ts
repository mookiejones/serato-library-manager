import { describe, expect, it } from "vitest";

import {
  BLOCKED_MESSAGE,
  canAdvance,
  canGoBack,
  createWizard,
  primaryAction,
  primaryEnabled,
  reduceWizard,
  snapshotBlocked,
  stepAnnouncement,
  stepPosition,
  visibleSteps,
  type WizardModel,
} from "./wizard";

function model(overrides?: {
  needsConsent?: boolean;
  library?: WizardModel["context"]["library"];
  seratoRunning?: boolean;
}): WizardModel {
  return createWizard({
    needsConsent: overrides?.needsConsent ?? true,
    library: overrides?.library ?? "found",
    seratoRunning: overrides?.seratoRunning ?? false,
  });
}

function atSnapshot(source: WizardModel, phase: WizardModel["context"]["snapshot"] = "idle"): WizardModel {
  let current = reduceWizard(source, { type: "next" });
  current = reduceWizard(current, { type: "next" });
  if (phase !== "idle") current = reduceWizard(current, { type: "snapshot", phase });
  return current;
}

describe("step list", () => {
  it("asks the sharing question only when no choice is saved", () => {
    expect(visibleSteps(true)).toEqual(["welcome", "library", "snapshot", "consent", "done"]);
    expect(visibleSteps(false)).toEqual(["welcome", "library", "snapshot", "done"]);
  });

  it("numbers the welcome step as step 1", () => {
    const start = model();
    expect(stepPosition(start)).toEqual({ index: 1, count: 5, name: "Welcome" });
    expect(stepAnnouncement(start)).toBe("Step 1 of 5. Welcome.");
    expect(canGoBack(start)).toBe(false);
    expect(primaryAction(start)).toBe("get-started");
  });

  it("uses four steps when sharing was already chosen", () => {
    const library = reduceWizard(model({ needsConsent: false }), { type: "next" });
    expect(stepPosition(library)).toEqual({ index: 2, count: 4, name: "Find your library" });
  });
});

describe("back and cancel", () => {
  it("moves back one step and does not finish setup", () => {
    const library = reduceWizard(model(), { type: "next" });
    expect(library.step).toBe("library");
    expect(canGoBack(library)).toBe(true);
    const welcome = reduceWizard(library, { type: "back" });
    expect(welcome.step).toBe("welcome");
    expect(welcome.complete).toBe(false);
    expect(reduceWizard(welcome, { type: "back" }).step).toBe("welcome");
  });

  it("returns to the snapshot from done when sharing is skipped", () => {
    let current = model({ needsConsent: false });
    current = reduceWizard(current, { type: "next" });
    current = reduceWizard(current, { type: "next" });
    current = reduceWizard(current, { type: "snapshot", phase: "saved" });
    current = reduceWizard(current, { type: "next" });
    expect(current.step).toBe("done");
    expect(reduceWizard(current, { type: "back" }).step).toBe("snapshot");
  });

  it("returns to sharing from done, and keeps the saved safety copy", () => {
    let current = atSnapshot(model(), "saved");
    current = reduceWizard(current, { type: "next" });
    expect(current.step).toBe("consent");
    current = reduceWizard(current, { type: "consent", value: false });
    expect(current.step).toBe("done");
    expect(current.context.consent).toBe(false);
    const back = reduceWizard(current, { type: "back" });
    expect(back.step).toBe("consent");
    expect(back.context.snapshot).toBe("saved");
    expect(back.complete).toBe(false);
  });

  it("cancels from every step without marking setup complete", () => {
    const steps: WizardModel[] = [];
    let current = model();
    steps.push(current);
    current = reduceWizard(current, { type: "next" });
    steps.push(current);
    current = atSnapshot(model(), "saved");
    steps.push(current);
    current = reduceWizard(current, { type: "next" });
    steps.push(current);
    current = reduceWizard(current, { type: "consent", value: true });
    steps.push(current);
    for (const step of steps) {
      const cancelled = reduceWizard(step, { type: "cancel" });
      expect(cancelled.dismissed).toBe(true);
      expect(cancelled.complete).toBe(false);
      expect(reduceWizard(cancelled, { type: "finish" }).complete).toBe(false);
    }
  });

  it("does not go back while the safety copy is saving", () => {
    const saving = atSnapshot(model(), "saving");
    expect(canGoBack(saving)).toBe(false);
    expect(reduceWizard(saving, { type: "back" }).step).toBe("snapshot");
    const cancelled = reduceWizard(saving, { type: "cancel" });
    expect(cancelled.dismissed).toBe(true);
    expect(cancelled.complete).toBe(false);
  });
});

describe("Serato DJ block", () => {
  it("disables the safety copy while Serato DJ is running", () => {
    const blocked = atSnapshot(model({ seratoRunning: true }));
    expect(blocked.step).toBe("snapshot");
    expect(snapshotBlocked(blocked)).toBe(true);
    expect(primaryEnabled(blocked)).toBe(false);
    expect(primaryAction(blocked)).toBe("take-snapshot");
    expect(BLOCKED_MESSAGE).toBe("Close Serato DJ to continue.");
    expect(canAdvance(blocked)).toBe(false);
    expect(reduceWizard(blocked, { type: "next" }).step).toBe("snapshot");
  });

  it("enables the safety copy when the re-check says Serato DJ has quit", () => {
    const blocked = atSnapshot(model({ seratoRunning: true }));
    const open = reduceWizard(blocked, { type: "serato", running: false });
    expect(snapshotBlocked(open)).toBe(false);
    expect(primaryEnabled(open)).toBe(true);
    expect(primaryAction(open)).toBe("take-snapshot");
  });

  it("blocks again if Serato DJ starts before the copy is saved", () => {
    const ready = atSnapshot(model());
    const blocked = reduceWizard(ready, { type: "serato", running: true });
    expect(snapshotBlocked(blocked)).toBe(true);
    expect(primaryEnabled(blocked)).toBe(false);
  });

  it("lets Continue work after the copy is saved", () => {
    let current = atSnapshot(model({ seratoRunning: true }), "saved");
    expect(snapshotBlocked(current)).toBe(false);
    expect(primaryAction(current)).toBe("continue");
    expect(primaryEnabled(current)).toBe(true);
    current = reduceWizard(current, { type: "next" });
    expect(current.step).toBe("consent");
  });
});

describe("completion", () => {
  it("stays incomplete until Open my library on the last step", () => {
    let current = atSnapshot(model({ needsConsent: false }), "saved");
    current = reduceWizard(current, { type: "next" });
    expect(current.step).toBe("done");
    expect(current.complete).toBe(false);
    expect(reduceWizard(current, { type: "finish", }).complete).toBe(true);
    expect(reduceWizard(atSnapshot(model(), "saved"), { type: "finish" }).complete).toBe(false);
  });

  it("does not advance past the library until one is found", () => {
    let current = reduceWizard(model({ library: "missing" }), { type: "next" });
    expect(current.step).toBe("library");
    expect(primaryAction(current)).toBe("check-again");
    expect(canAdvance(current)).toBe(false);
    expect(reduceWizard(current, { type: "next" }).step).toBe("library");
    current = reduceWizard(current, { type: "library", status: "found" });
    expect(primaryAction(current)).toBe("use-library");
    expect(reduceWizard(current, { type: "next" }).step).toBe("snapshot");
  });

  it("does not leave the snapshot step until the copy is saved", () => {
    const waiting = atSnapshot(model());
    expect(primaryAction(waiting)).toBe("take-snapshot");
    expect(reduceWizard(waiting, { type: "next" }).step).toBe("snapshot");
    const failed = reduceWizard(waiting, { type: "snapshot", phase: "error" });
    expect(primaryAction(failed)).toBe("try-again");
    expect(reduceWizard(failed, { type: "next" }).step).toBe("snapshot");
    const saved = reduceWizard(failed, { type: "snapshot", phase: "saved" });
    expect(reduceWizard(saved, { type: "next" }).step).toBe("consent");
  });
});
