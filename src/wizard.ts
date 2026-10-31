/**
 * First-run wizard state machine.
 *
 * The steps are welcome, find the library, take a safety snapshot, the
 * sharing question when it has not been answered, and done. Back and
 * Cancel never mark setup complete. The snapshot step stays blocked
 * while Serato DJ is running until the safety copy has been saved.
 */

export type WizardStep = "welcome" | "library" | "snapshot" | "consent" | "done";

export type LibraryStatus = "pending" | "found" | "missing" | "error";

export type SnapshotPhase = "idle" | "saving" | "saved" | "error";

export type PrimaryAction =
  | "get-started"
  | "looking"
  | "use-library"
  | "check-again"
  | "take-snapshot"
  | "try-again"
  | "continue"
  | "open-library"
  | "none";

export interface WizardContext {
  needsConsent: boolean;
  library: LibraryStatus;
  seratoRunning: boolean;
  snapshot: SnapshotPhase;
  consent: boolean | null;
}

export interface WizardModel {
  step: WizardStep;
  complete: boolean;
  dismissed: boolean;
  context: WizardContext;
}

export type WizardAction =
  | { type: "next" }
  | { type: "back" }
  | { type: "cancel" }
  | { type: "library"; status: LibraryStatus }
  | { type: "serato"; running: boolean }
  | { type: "snapshot"; phase: SnapshotPhase }
  | { type: "consent"; value: boolean }
  | { type: "finish" };

export interface StepPosition {
  index: number;
  count: number;
  name: string;
}

import { t, type MessageKey } from "./i18n";

// English source text, kept for callers and tests. The screen uses t().
export const BLOCKED_MESSAGE = "Close Serato DJ to continue.";

export const DONE_MESSAGE = "Library ready. Snapshot saved.";

export const WELCOME_BODY =
  "This app shows the library Serato already keeps on this computer. It will not change anything without asking.";

export const SNAPSHOT_BODY =
  "A backup of your library data is saved before anything is changed.";

export const CONSENT_BODY =
  "Counts and actions only, plus the app name, the app version, and the operating system. Track titles, crate names, file paths, and library contents stay on this computer. Sharing stays off unless you turn it on.";

const STEP_NAME: Record<WizardStep, MessageKey> = {
  welcome: "wizard.step.welcome",
  library: "wizard.step.library",
  snapshot: "wizard.step.snapshot",
  consent: "wizard.step.consent",
  done: "wizard.step.done",
};

/**
 * Steps that should be on screen for this setup.
 *
 * The sharing step is omitted once a choice is already saved.
 */
export function visibleSteps(needsConsent: boolean): readonly WizardStep[] {
  const steps: WizardStep[] = ["welcome", "library", "snapshot"];
  if (needsConsent) steps.push("consent");
  steps.push("done");
  return steps;
}

/** Start on Welcome. Nothing is marked complete. */
export function createWizard(input: {
  needsConsent: boolean;
  library: LibraryStatus;
  seratoRunning: boolean;
}): WizardModel {
  return {
    step: "welcome",
    complete: false,
    dismissed: false,
    context: {
      needsConsent: input.needsConsent,
      library: input.library,
      seratoRunning: input.seratoRunning,
      snapshot: "idle",
      consent: null,
    },
  };
}

/** Apply one action. A finished or cancelled wizard ignores later actions. */
export function reduceWizard(model: WizardModel, action: WizardAction): WizardModel {
  if (model.dismissed || model.complete) return model;
  switch (action.type) {
    case "cancel":
      return { ...model, dismissed: true, complete: false };
    case "back":
      return goBack(model);
    case "next":
      return goNext(model);
    case "library":
      return { ...model, context: { ...model.context, library: action.status } };
    case "serato":
      return { ...model, context: { ...model.context, seratoRunning: action.running } };
    case "snapshot":
      return { ...model, context: { ...model.context, snapshot: action.phase } };
    case "consent":
      return goNext({ ...model, context: { ...model.context, consent: action.value } });
    case "finish":
      if (model.step !== "done") return model;
      return { ...model, complete: true };
    default:
      return model;
  }
}

/** 1-based position among the steps this run shows. */
export function stepPosition(model: WizardModel): StepPosition {
  const steps = visibleSteps(model.context.needsConsent);
  const found = steps.indexOf(model.step);
  const index = found < 0 ? 1 : found + 1;
  return { index, count: steps.length, name: t(STEP_NAME[model.step]) };
}

/** Welcome has no Back. Back is also off while a safety copy is saving. */
export function canGoBack(model: WizardModel): boolean {
  if (model.dismissed || model.complete) return false;
  if (model.step === "snapshot" && model.context.snapshot === "saving") return false;
  return visibleSteps(model.context.needsConsent).indexOf(model.step) > 0;
}

/** True when Next would move to the following step. */
export function canAdvance(model: WizardModel): boolean {
  if (model.dismissed || model.complete) return false;
  switch (model.step) {
    case "welcome":
      return true;
    case "library":
      return model.context.library === "found";
    case "snapshot":
      return model.context.snapshot === "saved";
    case "consent":
      return model.context.consent !== null;
    case "done":
      return false;
    default:
      return false;
  }
}

/**
 * True when the snapshot step must wait for Serato DJ to quit.
 *
 * A safety copy that already finished does not stay blocked.
 */
export function snapshotBlocked(model: WizardModel): boolean {
  return (
    model.step === "snapshot" &&
    model.context.seratoRunning &&
    model.context.snapshot !== "saved"
  );
}

/** The verb button for this step, or none when the step has two choices. */
export function primaryAction(model: WizardModel): PrimaryAction {
  switch (model.step) {
    case "welcome":
      return "get-started";
    case "library":
      if (model.context.library === "pending") return "looking";
      if (model.context.library === "found") return "use-library";
      return "check-again";
    case "snapshot":
      if (model.context.snapshot === "saved") return "continue";
      if (model.context.snapshot === "error") return "try-again";
      return "take-snapshot";
    case "consent":
      return "none";
    case "done":
      return "open-library";
    default:
      return "none";
  }
}

/** Whether the primary button accepts a click. */
export function primaryEnabled(model: WizardModel): boolean {
  if (model.dismissed || model.complete) return false;
  const action = primaryAction(model);
  if (action === "none" || action === "looking") return false;
  if (model.step === "snapshot" && model.context.snapshot === "saving") return false;
  if (snapshotBlocked(model)) return false;
  return true;
}

/** Sentence for the live region, including the step numbers. */
export function stepAnnouncement(model: WizardModel): string {
  const position = stepPosition(model);
  return t("wizard.announce", { index: position.index, count: position.count, name: position.name });
}

function goBack(model: WizardModel): WizardModel {
  if (!canGoBack(model)) return model;
  const steps = visibleSteps(model.context.needsConsent);
  const index = steps.indexOf(model.step);
  const previous = steps[index - 1];
  if (previous === undefined) return model;
  return { ...model, step: previous };
}

function goNext(model: WizardModel): WizardModel {
  if (!canAdvance(model)) return model;
  const steps = visibleSteps(model.context.needsConsent);
  const index = steps.indexOf(model.step);
  const next = steps[index + 1];
  if (next === undefined) return model;
  return { ...model, step: next };
}
