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
  LogsPayload,
  MergePreview,
  RelatedPayload,
  RekordboxReport,
  RestorePlan,
  SeratoStatus,
  SettingsPayload,
} from "./api-types";

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
  return new Error(typeof error === "string" ? error : "Request failed");
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
export async function postJSON<T = ServerReply>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await readJSONOr<T & ErrorBody>(response, {} as T & ErrorBody);
  if (!response.ok) {
    const error = new Error(payload.error || `Request failed (${response.status})`) as ApiFailure;
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}
