/**
 * JSON fetch helpers for the local library server.
 *
 * postJSON attaches the HTTP status on a failed response so a 409 lock
 * can be recognized. The casts are erased. The request itself is unchanged.
 */

import type {
  CrateWriteResult,
  ErrorBody,
  FilesPayload,
  LibraryRoot,
  LibraryRootKind,
  LibraryRootsPayload,
  LogsPayload,
  MergePreview,
  RelatedPayload,
  RekordboxReport,
  RestorePlan,
  SeratoStatus,
  SettingsPayload,
  VersionPayload,
} from "./api-types";
import { serverMessage, t } from "./i18n";

export type ServerReply =
  & CrateWriteResult
  & FilesPayload
  & MergePreview
  & RelatedPayload
  & SettingsPayload
  & RestorePlan
  & ErrorBody
  & LogsPayload
  & RekordboxReport;

export interface ApiFailure extends Error {
  status?: number;
  payload?: ErrorBody;
}

export async function readJSON<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

export async function readJSONOr<T>(response: Response, fallback: T): Promise<T> {
  return await response.json().catch(() => fallback) as T;
}

export function failureOf(error: unknown): ApiFailure {
  if (error instanceof Error) return error as ApiFailure;
  return new Error(typeof error === "string" ? error : t("error.requestFailed"));
}

export function seratoFrom(error: unknown): SeratoStatus | null {
  const payload = failureOf(error).payload;
  return payload?.serato ?? null;
}

/**
 * POST a JSON body and return the decoded payload.
 *
 * Sends Content-Type application/json. A failed response becomes an Error
 * with status and payload so callers can recognize a 409 lock.
 */
const ROOT_KINDS: readonly LibraryRootKind[] = ["music_library", "serato_drive", "user_folder"];

/**
 * Return whether a JSON value is one library root.
 *
 * @param value Candidate from GET /api/library-roots.
 * @returns True when every contract field has the right type.
 */
export function isLibraryRoot(value: unknown): value is LibraryRoot {
  if (!value || typeof value !== "object") return false;
  const record = value as LibraryRoot;
  return typeof record.id === "string"
    && typeof record.path === "string"
    && typeof record.label === "string"
    && typeof record.detail === "string"
    && ROOT_KINDS.includes(record.kind)
    && typeof record.serato === "boolean"
    && typeof record.removable === "boolean"
    && typeof record.missing === "boolean";
}

/**
 * Read the music roots for this launch.
 *
 * `refresh` asks the server to recompute. Otherwise the cached list is
 * returned, including `computed_at` from that read.
 *
 * @param refresh When true, send `refresh=1`.
 * @returns The roots and the time they were computed.
 */
export async function fetchLibraryRoots(refresh = false): Promise<LibraryRootsPayload> {
  const response = await fetch(refresh ? "/api/library-roots?refresh=1" : "/api/library-roots");
  const payload = await readJSONOr<LibraryRootsPayload & ErrorBody>(response, {
    roots: [],
    computed_at: "",
  });
  if (!response.ok) {
    const error = new Error(serverMessage(payload, t("files.rootsUnreadable"))) as ApiFailure;
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return {
    roots: Array.isArray(payload.roots) ? payload.roots.filter(isLibraryRoot) : [],
    computed_at: typeof payload.computed_at === "string" ? payload.computed_at : "",
  };
}

function isVersionSource(value: unknown): value is VersionPayload["source"] {
  return value === "release" || value === "git" || value === "dev";
}

/**
 * Return whether a JSON value is the GET /api/version object.
 *
 * The three fields are version, commit, and source. commit may be null.
 * A wrong type is not a version, including an error object from another route.
 *
 * @param value Parsed JSON.
 * @returns True when the contract fields have the right types.
 */
export function isVersionPayload(value: unknown): value is VersionPayload {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.version === "string"
    && record.version.trim() !== ""
    && (record.commit === null || typeof record.commit === "string")
    && isVersionSource(record.source);
}

/**
 * Read the app version from GET /api/version.
 *
 * A failed response, a non-JSON body, and a body that is not the version
 * object all reject. The rejection message is the same plain sentence the
 * page shows. It is not the server's error text.
 *
 * @returns version, commit, and source.
 */
export async function getVersion(): Promise<VersionPayload> {
  const response = await fetch("/api/version");
  const payload: unknown = await readJSONOr<unknown>(response, null);
  if (!response.ok || !isVersionPayload(payload)) {
    throw new Error(t("version.unavailable"));
  }
  return {
    version: payload.version.trim(),
    commit: payload.commit,
    source: payload.source,
  };
}

export async function postJSON<T = ServerReply>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await readJSONOr<T & ErrorBody>(response, {} as T & ErrorBody);
  if (!response.ok) {
    const error = new Error(serverMessage(payload, t("error.requestStatus", { status: String(response.status) }))) as ApiFailure;
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}
