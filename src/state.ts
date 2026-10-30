/**
 * Page state for the library screen.
 *
 * The server remains the source of truth. This object is the last payload
 * plus the view the user has open. ROW matches --row in app.css.
 * FILE_ROW matches --file-row.
 */

import type {
  Crate,
  DuplicateGroup,
  FileCrumb,
  FileEntry,
  FileRoot,
  LibraryRoot,
  HistorySession,
  PendingUndo,
  SeratoStatus,
  SnapshotInfo,
  Track,
} from "./api-types";
import type { MessageKey } from "./i18n";

// Row height in pixels. It matches --row in app.css. The painter divides
// the scroll offset by this value, so the two must stay equal.
export const ROW = 36;
export const FILE_ROW = 44;
export const ROOT_ROW = 64;

// The second item is the message key for the color name.
export const COLORS: Array<[number, MessageKey]> = [
  [0xffffff, "color.none"],
  [0xcc0000, "color.red"],
  [0xff8800, "color.orange"],
  [0xffcc00, "color.yellow"],
  [0x33aa55, "color.green"],
  [0x2255cc, "color.blue"],
  [0x8833cc, "color.purple"],
  [0xe23b8a, "color.pink"],
];

export const COLOR_NAMES: Record<string, number> = {
  none: 0xffffff,
  red: 0xcc0000,
  orange: 0xff8800,
  yellow: 0xffcc00,
  green: 0x33aa55,
  blue: 0x2255cc,
  purple: 0x8833cc,
  pink: 0xe23b8a,
};

export interface PageState {
  tracks: Track[];
  byId: Map<number, Track>;
  crates: Crate[];
  crateTracks: Map<number, Set<number>>;
  rootId: number | null | undefined;
  activeCrate: number | "all";
  query: string;
  crateQuery: string;
  crateSort: string;
  sort: string;
  sortDir: number;
  selectedId: number | null;
  request: number;
  expanded: Set<number | "all">;
  space: string;
  mode: string;
  writable: boolean;
  serato: SeratoStatus | null | undefined;
  historySessions: HistorySession[];
  historyId: number | null;
  entries: Track[];
  duplicateIds: Set<number> | null;
  duplicateGroups: DuplicateGroup[];
  duplicateSpace: string;
  telemetryConsent: boolean | null;
  telemetryConfigured: boolean;
  wizardComplete: boolean;
  filesPath: string;
  filesParent: string | null;
  filesEntries: FileEntry[];
  filesSelected: Set<string>;
  filesPick: "move" | "move_folder" | null;
  filesPickPaths: string[];
  filesPickSource: string;
  filesLoading: boolean;
  filesError: string;
  filesMessage: string;
  filesTruncated: boolean;
  filesAtRoots: boolean;
  filesRoots: LibraryRoot[];
  filesRoot: FileRoot | null;
  filesBreadcrumb: FileCrumb[];
  filesElsewhere: boolean;
  filesActive: number;
  filesQuery: string;
  filesSearching: boolean;
  snapshots: SnapshotInfo[];
  snapshotLoading: boolean;
  snapshotError: string;
  snapshotMessage: MessageKey | "";
  snapshotUndo: PendingUndo | null;
  writeBlock: string;
  writeBlockCode: string;
  writeBlockParams: Record<string, string | number> | null;
  seratoRunning: boolean;
  snapshotPlanId: string;
  view: Track[];
}

export const state: PageState = {
  tracks: [],
  byId: new Map(),
  crates: [],
  crateTracks: new Map(),
  rootId: null,
  activeCrate: "all",
  query: "",
  crateQuery: "",
  crateSort: "order",
  sort: "name",
  sortDir: 1,
  selectedId: null,
  request: 0,
  expanded: new Set(),
  space: "Serato Library",
  mode: "crates",
  writable: false,
  serato: null,
  historySessions: [],
  historyId: null,
  entries: [],
  duplicateIds: null,
  duplicateGroups: [],
  duplicateSpace: "",
  telemetryConsent: null,
  telemetryConfigured: false,
  wizardComplete: false,
  filesPath: "",
  filesParent: null,
  filesEntries: [],
  filesSelected: new Set(),
  filesPick: null,
  filesPickPaths: [],
  filesPickSource: "",
  filesLoading: false,
  filesError: "",
  filesMessage: "",
  filesTruncated: false,
  filesAtRoots: false,
  filesRoots: [],
  filesRoot: null,
  filesBreadcrumb: [],
  filesElsewhere: false,
  filesActive: 0,
  filesQuery: "",
  filesSearching: false,
  snapshots: [],
  snapshotLoading: false,
  snapshotError: "",
  snapshotMessage: "",
  snapshotUndo: null,
  writeBlock: "",
  writeBlockCode: "",
  writeBlockParams: null,
  seratoRunning: false,
  snapshotPlanId: "",
  view: [],
};
