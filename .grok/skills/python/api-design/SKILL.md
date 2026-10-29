---
name: designing-python-apis
description: Keeps the local HTTP routes in server.py consistent — the same JSON shape, the same error contract, and additive changes the page can still read. Use when adding or changing a /api/* route, a status code, or a response field src/api.ts reads.
---

# Local API routes

`server.py` is the API. `src/api.ts` is the client. Both ship in the same commit. There is no installed package, so public re-exports, `__all__`, and deprecation warnings do not apply. Keep three things steady: routes that work the same way, one error contract, and changes the current page can still read.

## Consistency

GET reads. POST edits, reveals a file, saves settings, or asks the desktop process to shut down or focus. A new route picks the verb the existing ones use. Do not add a GET that writes.

| Kind | Where the input lives | Examples |
| --- | --- | --- |
| Read | Query string | `/api/library?space=`, `/api/track?id=`, `/api/files?path=` |
| Edit | JSON object body | `/api/track`, `/api/crate`, `/api/files`, `/api/snapshots` |
| Desktop control | Empty or ignored body, token in the handler | `/api/shutdown`, `/api/focus` |

Success and failure are both JSON objects from `send_json`, except a file download (`/api/export.m3u`, `/api/export.rekordbox.xml` without `report=1`) and a static file. `send_file` is only for `static/`. A GET path that matches no route falls through to `send_file` and answers 404 when the file is missing. Do not treat that HTML 404 as the API error. An unknown POST path answers `{"error": "That action is not available."}` with status 404.

Use the words the page already uses (`space`, `crate`, `preview`, `confirm`, `id`). A boolean in a JSON body is a JSON boolean (`"confirm": true`). The Rekordbox GET query uses `"1"` and `"0"` for `memory` and `hot_loops`. A new flag on that same query uses that spelling. Do not add a second spelling for one flag.

The server binds `127.0.0.1` only. A route does not change that.

## Error contract

`postJSON` in `src/api.ts` reads `payload.error` as the sentence the UI shows, and `payload.serato` to recognize a 409 lock. Every JSON failure keeps that shape. `ErrorBody` in `src/api-types.ts` is `error?: string` and `serato?: SeratoStatus | null`.

| Situation | Status | Body |
| --- | --- | --- |
| Track id missing, body not JSON, body not an object, or a value of the wrong type | 400 | `{"error": "..."}` — a specific sentence when one exists (`"Track id is required."`, `"The request body is not JSON."`), otherwise `"That request is not valid."` |
| Track not in the requested space, or no library file | 404 | `{"error": "Track is not in this space."}` or `{"error": "No Serato library was found on this computer."}` |
| POST path the handler does not implement | 404 | `{"error": "That action is not available."}` |
| Serato holds the library, or SQLite reports the database locked | 409 | `{"error": "...", "serato": <status object>}` |
| Body larger than `BODY_LIMIT` | 413 | `{"error": "That upload is too large."}` |
| Shutdown route with no desktop token | 404 | The route is absent when `server.py` is run on its own |
| Shutdown route with the wrong token | 403 | Comparison does not reveal which character differed |
| Any other exception | 500 | `{"error": "Something went wrong. The details are in the local log."}` |

`library.LibraryError` and `snapshots.SnapshotError` carry their own status and message and are sent as `{"error": exc.message}`. A Serato lock uses `LibraryError` or `SeratoOpen` with the `serato` object and status 409.

Rules that keep a failure from looking like success:

- Do not answer 200 when the write did not happen. A preview sets `preview: true` and describes the change. `confirm: true` is what performs it.
- `_report_failure` logs the traceback and returns the fixed 500 sentence. The JSON does not include the exception text. That text can contain a path.
- Validate the body before the first mutation. A 400 that arrives after a row or a file has changed breaks the contract. See `destructive-operations`.
- An empty list is a real empty result (no tracks, no snapshots). It is not a stand-in for a failed read. If the read failed, send an error status.
- Opening the logs folder ignores the body. The response does not include the folder path.

## Evolution

The page and the server move together. There is no external caller to warn, and no deprecation cycle.

Safe in one commit, with the TypeScript type updated when the page reads the field:

- Add a JSON field the current page ignores.
- Add a query parameter with a default equal to today's behavior (`crate` defaults to `all`, `memory` defaults to on).
- Add a route that follows the error contract above.

Breaking, and only with the page updated in the same commit:

- Rename or remove a field `src/` reads.
- Change a status the page branches on (409 for the Serato lock, 400 for a bad body, 404 for a missing track).
- Change `"1"` / `"0"` on an existing GET flag, or the meaning of `preview` and `confirm`.
- Put a path or an exception string in an error body.

`docs/architecture.md` describes the routes. Update it in the same change as the route.

## Checklist

```
Consistency:
- [ ] GET reads, POST writes, matching the routes already in server.py
- [ ] Input is a query on GET and a JSON object on POST
- [ ] Field names match src/api-types.ts

Errors:
- [ ] Failure is {"error": string} and, for a Serato lock, {"error", "serato"} with status 409
- [ ] 500 text is the fixed sentence, with the traceback only in the local log
- [ ] Validation happens before the first write
- [ ] An empty payload is not used to hide a failed read

Evolution:
- [ ] A removed or renamed field is updated in src/ in the same commit
- [ ] docs/architecture.md matches the route
```
