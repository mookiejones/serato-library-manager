/**
 * JSON shapes the page reads from the local library server.
 *
 * These types describe the fields the screen uses. They are not a second
 * copy of the database schema. A missing key is undefined at runtime, and
 * the page already treats that as empty.
 */

export interface SeratoStatus {
  writable?: boolean;
  message?: string;
  file_manager?: string;
  open?: boolean;
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
  stems?: boolean;
  entry?: boolean;
  deck?: string;
  played?: string;
  start?: number | string | null;
  file_size?: number | string | null;
  file_on_disk?: boolean;
  in_prepare?: boolean;
  play_count?: number | null;
  comments?: string;
  resolved_path?: string;
  crate_ids?: number[];
  serato?: SeratoStatus | null;
  edit?: EditFields;
  cues?: Marker[];
  loops?: Marker[];
  flips?: Flip[];
  beatgrid?: Marker[];
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

export interface LibraryPayload {
  tracks: Track[];
  crates: Crate[];
  root_id?: number | null;
  serato?: SeratoStatus | null;
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
  [key: string]: string | number | boolean | null | undefined;
}

export interface HistoryPayload {
  sessions?: HistorySession[];
  entries?: Track[];
  error?: string;
}

export interface FileEntry {
  name: string;
  kind: string;
  path: string;
  in_library?: boolean;
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
}

export interface FilesBody {
  action: string;
  confirm?: boolean;
  path?: string;
  name?: string;
  paths?: string[];
  destination?: string;
  replacement?: string;
}

export interface MergeCrate {
  name?: string;
  space?: string;
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

export interface SettingsPayload {
  telemetry_consent?: boolean | null;
  telemetry_configured?: boolean;
  needs_consent_prompt?: boolean;
  app_version?: string;
  rekordbox?: RekordboxSettings;
  error?: string;
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

export interface FrameDiff {
  path?: string;
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
  dry_run?: boolean;
  restore_blocked?: string | null;
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
}

export interface PendingUndo {
  restore_id?: string;
  source?: string;
}

export interface SnapshotList {
  snapshots?: SnapshotInfo[];
  pending_undo?: PendingUndo | null;
  write_block?: string;
  serato_running?: boolean;
  error?: string;
}

export interface ErrorBody {
  error?: string;
  serato?: SeratoStatus | null;
}
