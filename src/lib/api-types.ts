/**
 * JSON shapes the page reads from the local library server.
 *
 * These types describe the fields the screen uses. They are not a second
 * copy of the database schema. A missing key is undefined at runtime, and
 * the page already treats that as empty.
 */

export interface LibraryGeneration {
  kind?: string;
  source?: string;
  version?: string;
  build?: string;
  newest_version?: string;
  database?: string;
  log_name?: string;
  mounted?: boolean | null;
  downgrade?: boolean;
  confirmed?: boolean | null;
  reason?: string;
  install_version?: string;
}

export interface SeratoStatus {
  writable?: boolean;
  message?: string;
  file_manager?: string;
  open?: boolean;
  /** Stable code when `message` is a translated notice. */
  code?: string;
  /** Placeholder values for `code`, such as the Serato build. */
  params?: Record<string, string>;
  /** Serato 4, Serato 5, or unknown, and why that was chosen. */
  generation?: LibraryGeneration;
}

export interface EditFields {
  color?: number | string | null;
  rating?: number | string | null;
  is_beatgrid_locked?: boolean | number | string | null;
  portable_id?: string;
  [key: string]: string | number | boolean | null | undefined;
}

export interface Marker {
  color?: string;
  start_ms?: number | string;
  end_ms?: number | string;
  name?: string;
  index?: number;
  locked?: boolean;
  position?: number | string | null;
  /** Stored beatgrid time in seconds. The panel string is `position`. */
  position_seconds?: number;
  bpm?: number | string | null;
  beats?: number | string | null;
}

export interface Flip {
  enabled?: boolean;
  name?: string;
  index?: number;
}

export interface CopyRow {
  id?: number;
  file?: string;
  bitrate?: number | string;
  missing?: boolean;
  crates?: string;
  play_count?: number | null;
}

export interface MembershipCrate {
  id: number;
  name?: string;
  smart?: boolean;
}

export type TrackValue =
  | string
  | number
  | boolean
  | null
  | SeratoStatus
  | EditFields
  | Marker[]
  | Flip[]
  | CopyRow[]
  | MembershipCrate[]
  | FieldGroup[]
  | number[]
  | string[];

export interface Track {
  id: number;
  name?: string;
  artist?: string;
  album?: string;
  genre?: string;
  key?: string;
  file?: string;
  title?: string;
  bpm?: number | string | null;
  length?: string;
  length_ms?: number | string | null;
  color?: number | string | null;
  emoji?: string;
  missing?: boolean;
  /** Unplugged-drive track. Distinct from `missing`. */
  offline?: boolean;
  /** Drive name when `offline` is set. */
  offline_drive?: string;
  stems?: boolean;
  entry?: boolean;
  deck?: string;
  played?: string;
  start?: number | string | null;
  file_size?: number | string | null;
  file_on_disk?: boolean;
  in_prepare?: boolean;
  play_count?: number | null;
  /** Serato star rating 0–1. The Energy column maps this to 1–5. */
  rating?: number | null;
  /** Unix seconds when the library row was added. */
  time_added?: number | string | null;
  /** Latest played history_entry.start_time, or null. */
  last_played?: number | string | null;
  /** Cue presence when the list already knows it. Omitted on GET /api/library. */
  has_cues?: boolean;
  comments?: string;
  grouping?: string;
  composer?: string;
  resolved_path?: string;
  crate_ids?: number[];
  serato?: SeratoStatus | null;
  edit?: EditFields;
  cues?: Marker[];
  loops?: Marker[];
  flips?: Flip[];
  beatgrid?: Marker[];
  beatgrid_warning?: string | null;
  beatgrid_warning_code?: string | null;
  markers_found?: boolean;
  markers_unavailable?: boolean;
  copies?: CopyRow[];
  crates?: MembershipCrate[] | string;
  groups?: FieldGroup[];
  asset_id?: number;
  notes?: string;
  start_time?: number | string | null;
  added?: number;
  order?: number;
  bitrate?: number | string;
  [key: string]: TrackValue | undefined;
}

export interface Crate {
  id: number;
  name: string;
  parent?: number | null;
  depth?: number;
  smart?: boolean;
  expanded?: boolean;
  tracks?: number[];
  color?: number | string | null;
  rules?: SmartCrateRules | null;
  count?: number | null;
  childCount?: number;
  holds?: boolean;
  added?: number;
  order?: number;
}

export interface SmartRule {
  field?: string;
  operator?: string;
  attribute?: string;
  operation?: string;
  value?: string | number | null;
}

export interface SmartCrateRules {
  rules?: SmartRule[];
  conjunction?: string;
}

export interface DetailField {
  label?: string;
  column?: string;
  display: string;
  value?: string | number | null;
}

export interface FieldGroup {
  name?: string;
  fields: DetailField[];
}

export interface RelatedHit {
  title?: string;
  name?: string;
  artist?: string;
  key?: string;
  bpm?: number | string | null;
  asset_id?: number;
  in_library?: boolean;
}

/** A crate preset as POST /api/smart-preset stores it. */
export type PresetSpec =
  | { kind: "harmonic"; key: string; crate?: number }
  | { kind: "bpm"; bpm: number; range: number; crate?: number }
  | { kind: "unplayed"; months: number; crate?: number };

/** One remembered preset crate in GET /api/library. */
export interface PresetRecord {
  preset: PresetSpec;
  updated?: number | null;
}

export interface LibraryPayload {
  tracks: Track[];
  crates: Crate[];
  root_id?: number | null;
  serato?: SeratoStatus | null;
  /** Preset crates of this space, keyed by crate id. */
  presets?: Record<string, PresetRecord>;
  error?: string;
}

export interface DuplicateGroup {
  ids?: number[];
}

export interface DuplicatePayload {
  groups?: DuplicateGroup[];
  error?: string;
}

export interface HistorySession {
  id: number;
  name?: string;
  start_time?: number | string | null;
  played?: number | string | null;
  [key: string]: string | number | boolean | null | undefined;
}

export interface HistoryPayload {
  sessions?: HistorySession[];
  entries?: Track[];
  error?: string;
}

export interface HistoryStatsTrack {
  asset_id?: number | null;
  id?: number;
  name?: string;
  artist?: string;
  plays?: number;
  last_played?: number | null;
  added?: number | null;
  play_count?: number;
}

export interface HistoryStatsArtist {
  artist?: string;
  plays?: number;
  tracks?: number;
  last_played?: number | null;
}

export interface HistoryStatsReport {
  from?: number | null;
  to?: number | null;
  plays?: number;
  sessions?: number;
  top_tracks?: HistoryStatsTrack[];
  top_artists?: HistoryStatsArtist[];
  idle_days?: number;
  not_played?: HistoryStatsTrack[];
  not_played_count?: number;
  error?: string;
  code?: string;
}

export interface HistoryIdleCrate {
  preview?: boolean;
  written?: boolean;
  name?: string;
  idle_days?: number;
  count?: number;
  id?: number;
  tracks?: HistoryStatsTrack[];
  warning?: string;
  error?: string;
}

export interface FileEntry {
  name: string;
  kind: string;
  path: string;
  in_library?: boolean;
  missing?: boolean;
  detail?: string;
  /** Music root that can leave the laptop. Absent on an ordinary folder row. */
  removable?: boolean;
  /** Music root Serato already uses. Absent on an ordinary folder row. */
  serato?: boolean;
  /** Present on a name search. Higher is a closer match. */
  score?: number;
}

export interface FileRoot {
  name: string;
  path: string;
  kind: string;
  missing?: boolean;
}

export type LibraryRootKind = "music_library" | "serato_drive" | "user_folder";

export interface LibraryRoot {
  id: string;
  path: string;
  label: string;
  detail: string;
  kind: LibraryRootKind;
  serato: boolean;
  removable: boolean;
  missing: boolean;
}

export interface LibraryRootsPayload {
  roots: LibraryRoot[];
  computed_at: string;
}

export interface FileCrumb {
  name: string;
  path: string;
}

export interface FileChange {
  from?: string;
  to?: string;
  effect?: string;
  crates?: string[];
}

export interface FilesPayload {
  path?: string;
  parent?: string | null;
  entries?: FileEntry[];
  search?: boolean;
  query?: string;
  roots?: FileRoot[];
  root?: FileRoot | null;
  breadcrumb?: FileCrumb[];
  elsewhere?: boolean;
  truncated?: boolean;
  serato?: SeratoStatus | null;
  error?: string;
  ok?: boolean;
  summary?: string;
  warning?: string;
  changes?: FileChange[];
  more?: number;
  needs_confirm?: boolean;
  browse?: string;
  skipped?: string[];
}

export interface FilesBody {
  action: string;
  confirm?: boolean;
  path?: string;
  name?: string;
  paths?: string[];
  destination?: string;
  replacement?: string;
  matches?: { id: number; path: string }[];
  crate?: number;
  space?: string;
}

export interface RelinkCandidate {
  path: string;
  confidence: string;
  reason: string;
}

export interface RelinkMatch {
  asset_id: number;
  title?: string;
  artist?: string;
  stored?: string;
  candidates?: RelinkCandidate[];
}

export interface RelinkRemap {
  from?: string;
  to?: string;
  count?: number;
}

export interface RelinkPlan {
  missing?: number;
  unavailable_drives?: string[];
  matches?: RelinkMatch[];
  remaps?: RelinkRemap[];
  scanned?: number;
  truncated?: boolean;
  error?: string;
  code?: string;
}

export interface MergeCrate {
  id?: number;
  name?: string;
  space?: string;
  list_order?: number | null;
}

export interface CratesReplacePreview {
  ok?: boolean;
  from_id?: number;
  to_id?: number;
  space?: string;
  from?: { id?: number; file?: string; name?: string; artist?: string };
  to?: { id?: number; file?: string; name?: string; artist?: string };
  crates_added?: MergeCrate[];
  crates_kept?: MergeCrate[];
  crates_removed?: MergeCrate[];
  retire?: boolean;
  writable?: boolean;
  preview?: boolean;
  warning?: string | null;
}

export interface MergeField {
  field?: string;
  label?: string;
  before?: string | number | null;
  after?: string | number | null;
}

export interface MergeFile {
  file?: string;
  reason?: string;
  on_disk?: boolean;
  blocks_trash?: boolean;
}

export interface MergeCueCopy {
  file?: string;
  markers?: boolean;
  beatgrid?: boolean;
  status?: string;
}

export interface MergePreview {
  crates_added?: MergeCrate[];
  crates_kept?: MergeCrate[];
  spaces_added?: string[];
  fields?: MergeField[];
  history_repointed?: boolean;
  history_entries?: number;
  removed?: Array<{ id?: number }>;
  files?: MergeFile[];
  cue_warning?: string;
  cue_copy?: MergeCueCopy | null;
  writable?: boolean;
  kept?: { file?: string };
  warning?: string;
  ok?: boolean;
  preview?: boolean;
}

export interface RelatedTrack {
  id?: number;
  asset_id?: number;
  name?: string;
  artist?: string;
  title?: string;
  file?: string;
  path?: string;
  note?: string;
  rating?: number | null;
  reasons?: string[];
  mutual?: boolean;
  in_library?: boolean;
  track?: RelatedHit;
}

export interface RelatedPayload {
  saved?: RelatedTrack[];
  suggested?: RelatedTrack[];
  crate_name?: string;
  error?: string;
  ok?: boolean;
  track?: { asset_id?: number; in_library?: boolean };
}

export interface RekordboxSettings {
  hot_loops?: boolean;
  memory_cues?: boolean;
  key_notation?: string;
}

export interface IconApplyResult {
  applied: boolean;
  platform: string;
  target: string;
  reason: string;
  colorway: string;
  follows_theme: boolean;
  href: string;
}

export interface SettingsPayload {
  telemetry_consent?: boolean | null;
  telemetry_configured?: boolean;
  needs_consent_prompt?: boolean;
  wizard_complete?: boolean;
  layout?: { track_list_width: number | null; drawer_open?: boolean | null };
  app_version?: string;
  rekordbox?: RekordboxSettings;
  /** Saved page language, or null to follow the OS. */
  language?: string | null;
  /** Theme id: serato-like, dark-club, light, or classic. */
  colorway?: string;
  /** True when the Dock or taskbar icon should match the theme. */
  icon_follows_theme?: boolean;
  /** Page icon for the saved choice. */
  icon_href?: string;
  /** Result of changing the running icon. Present after a theme save. */
  icon?: IconApplyResult;
  error?: string;
  code?: string;
}

/** JSON body of GET /api/version. commit is null when git cannot name one. */
export interface VersionPayload {
  version: string;
  commit: string | null;
  source: "release" | "git" | "dev";
}

export interface LogsPayload {
  text?: string;
  truncated?: boolean;
  error?: string;
}

export interface RekordboxReport {
  xml?: string;
  report?: string[];
  error?: string;
}

export interface CrateWriteResult {
  warning?: string;
  error?: string;
  id?: number;
  name?: string;
  added?: number;
  unmatched_count?: number;
}

export interface PlanName {
  name?: string;
  path?: string;
  drive_label?: string;
}

export interface PlanGroup {
  added?: PlanName[];
  removed?: PlanName[];
  changed?: PlanName[];
  unavailable?: PlanName[];
}

/** Markers2 cues, loops, and flips on one restore frame side. */
export interface FrameCueSet {
  cues?: Marker[];
  loops?: Marker[];
  flips?: Flip[];
}

export interface FrameDiff {
  path?: string;
  drive_id?: string;
  /** Cue set, grid markers, or null when that side has no file. */
  before?: FrameCueSet | unknown[] | null;
  after?: FrameCueSet | unknown[] | null;
}

export interface DeletedPlan {
  crates?: PlanName[];
  tracks?: PlanName[];
  cues?: FrameDiff[];
  grids?: FrameDiff[];
}

/** Dry-run restore plan from POST /api/snapshots action plan. */
export interface RestorePlan {
  crates?: PlanGroup;
  tracks?: PlanGroup;
  cues?: FrameDiff[];
  grids?: FrameDiff[];
  deleted?: DeletedPlan;
  /**
   * Crate files the snapshot database has not heard of. Restore writes
   * them into the library so Serato 4/5 does not delete them on launch.
   */
  crates_registered?: PlanName[];
  /** Crate files whose snapshot copy has no hash or could not be read. */
  crates_skipped?: PlanName[];
  /** English warning when crate files will not be registered. */
  registration_warning?: string | null;
  /** Catalog code for `registration_warning`. */
  registration_warning_code?: string | null;
  dry_run?: boolean;
  restore_blocked?: string | null;
  /** Catalog code for `restore_blocked` when that sentence can be translated. */
  restore_blocked_code?: string;
  /** Placeholder values for `restore_blocked_code`. */
  restore_blocked_params?: Record<string, string>;
  error?: string;
}

export interface SnapshotInfo {
  id: string;
  created?: string;
  trigger?: string;
  serato_version?: string;
  serato_build?: string;
  unavailable_drives?: string[];
  reason?: string;
  /** Hash check of the stored database copy. */
  integrity?: string;
  /** Optional byte size when the API sends one. */
  size?: number;
}

export interface PendingUndo {
  restore_id?: string;
  source?: string;
}

export interface DriveCopy {
  drive_id?: string;
  label?: string;
  role?: string;
  present?: boolean;
  status?: string;
  files?: number;
}

/** Newest finished plain backup, after its hashes have been checked. */
export interface DriveBackup {
  folder?: string;
  verified?: boolean;
  drives?: DriveCopy[];
}

export interface OperationEntry {
  time?: string;
  action?: string;
  operation?: string;
  target?: string;
  result?: string;
  verified?: boolean;
  rolled_back?: boolean;
  snapshot_before?: string | null;
  snapshot_after?: string | null;
}

export interface OperationList {
  operations?: OperationEntry[];
  error?: string;
  code?: string;
}

export interface SnapshotList {
  snapshots?: SnapshotInfo[];
  pending_undo?: PendingUndo | null;
  write_block?: string;
  /** Catalog code for `write_block` when that sentence can be translated. */
  write_block_code?: string;
  /** Placeholder values for `write_block_code`. */
  write_block_params?: Record<string, string>;
  serato_running?: boolean;
  drive_backup?: DriveBackup | null;
  error?: string;
}

export interface GigDeduction {
  code: string;
  points: number;
  hard_red: boolean;
  summary: string;
}

export interface GigChanges {
  crates_added: string[];
  crates_removed: string[];
  crates_edited: string[];
  tracks_added: string[];
  tracks_removed: string[];
  cues_edited: string[];
  grids_edited: string[];
  tags_edited: string[];
}

export interface GigReport {
  ready: boolean;
  score: number;
  hard_red: boolean;
  holding_it_back?: GigDeduction[];
  missing_files?: Array<{ path: string; title: string; artist: string; crate: string }>;
  unavailable_drives?: Array<{ name: string; track_count: number; crates: string[] }>;
  streaming_tracks?: Array<{ service: string; path: string; title: string; artist: string; crate: string }>;
  empty_crates?: Array<{ name: string; warning: string }>;
  snapshot_note?: string;
  changes?: GigChanges | null;
  scope?: { space: string; crate_id: number | null; crate_name: string | null };
  checked_at?: string;
  error?: string;
}

export interface TempoDriftFlag {
  id: number;
  name: string;
  artist: string;
  file: string;
  reasons: string[];
  bpm_min: number | null;
  bpm_max: number | null;
}

export interface TempoDriftReport {
  crate: number | null;
  checked: number;
  not_found: number;
  unreadable: number;
  too_quiet: number;
  unchecked: number;
  mapped: number;
  flags: TempoDriftFlag[];
  error?: string;
  code?: string;
}

export interface BitrateSuspect {
  id: number;
  name: string;
  artist: string;
  file: string;
  reason: string;
  stated_kbps: number | null;
  estimated_kbps: number | null;
  cutoff_hz: number;
}

export interface BitrateCheckReport {
  crate: number | null;
  checked: number;
  not_found: number;
  unreadable: number;
  too_quiet: number;
  unchecked: number;
  suspects: BitrateSuspect[];
  error?: string;
  code?: string;
}

export interface BitrateCratePlan extends BitrateCheckReport {
  preview: boolean;
  written: boolean;
  name: string;
  added: number;
  saved: { id: number; name: string } | null;
  warning?: string | null;
}

export interface FileScanProblem {
  id: number;
  name: string;
  artist: string;
  file: string;
  problem: string;
  detail: string;
}

export interface FileScanReport {
  depth: string;
  crate: number | null;
  checked: number;
  not_found: number;
  unchecked: number;
  counts?: Record<string, number>;
  problems?: FileScanProblem[];
  error?: string;
  code?: string;
}

export interface LibraryHealthTrack {
  id: number;
  name: string;
  artist: string;
  file: string;
}

export interface LibraryHealthSection {
  count: number;
  tracks: LibraryHealthTrack[];
}

export interface LibraryHealthFile {
  file: string;
  path: string;
}

export interface LibraryHealthFiles {
  count: number;
  files: LibraryHealthFile[];
}

export interface LibraryHealthDuplicateGroup {
  name: string;
  artist: string;
  seconds: number;
  ids: number[];
}

export interface AlbumArtCandidate {
  release_id: string;
  title: string;
  artist: string;
  mime: string;
  thumb: string;
}

export interface AlbumArtPlan {
  preview: boolean;
  written: boolean;
  id: number;
  name: string;
  artist: string;
  album: string;
  file: string;
  candidates: AlbumArtCandidate[];
  error?: string;
  code?: string;
}

export interface AlbumArtMissing {
  space: string;
  crate: number | null;
  checked: number;
  tracks: LibraryHealthTrack[];
  error?: string;
  code?: string;
}

export interface LibraryHealthReport {
  space: string;
  crate: number | null;
  checked: number;
  missing: LibraryHealthSection;
  no_bpm: LibraryHealthSection;
  no_key: LibraryHealthSection;
  no_beatgrid: LibraryHealthSection;
  no_artwork: LibraryHealthSection;
  empty_genre: LibraryHealthSection;
  no_crate: LibraryHealthSection;
  unused: LibraryHealthFiles;
  duplicates: { count: number; groups: LibraryHealthDuplicateGroup[] };
  error?: string;
  code?: string;
}

export interface TagSpelling {
  value: string;
  count: number;
}

export interface TagClusterGroup {
  key: string;
  suggested: string;
  tracks: number;
  spellings: TagSpelling[];
}

export interface TagClusters {
  field: string;
  values: number;
  groups: TagClusterGroup[];
  error?: string;
  code?: string;
}

export interface TagClusterChange {
  id: number;
  from: string;
  to: string;
  remixer?: string;
  field?: string;
}

export interface TagClusterPlan {
  field: string;
  value: string;
  key: string;
  changes: TagClusterChange[];
  written: boolean;
  error?: string;
  code?: string;
}

export interface ErrorBody {
  error?: string;
  /** Stable code for a known error sentence. The page translates it. */
  code?: string;
  /** Placeholder values for a parameterized `code`. */
  params?: Record<string, string>;
  serato?: SeratoStatus | null;
}
