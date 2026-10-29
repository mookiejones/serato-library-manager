---
name: auditing-python-security
description: Reviews this app's dependency pins, Bandit findings, secrets, and path checks. Use when changing requirements, server.py file serving, files.py moves, or anything that reads a path or a secret from the environment. pip-audit already runs in CI.
---

# Security review

The process listens on `127.0.0.1` and reads a Serato library plus audio files on the same machine. The checks that matter are the pinned requirements, Bandit on the Python, secrets staying out of git and out of responses, and paths that cannot climb out of the directory they name.

This is not a library publish. There is no package index token, no Semgrep job, and no detect-secrets baseline. Do not add those to match a generic Python-library scan.

## pip-audit

CI already audits the pins. The `dependency audit` job in `.github/workflows/ci.yml` runs:

```bash
python -m pip install pip-audit==2.10.1
pip-audit --requirement requirements.txt --requirement requirements-build.txt --vulnerability-service osv
```

That command does not read `requirements-macos.txt` or `docs/requirements-docs.txt`. A new pin in the two files the job lists is what CI will fail on. Re-run the same command locally before pushing a requirements change.

`pip-audit --fix` rewrites pins. Do not use it to silence a finding without reading the advisory. The requirements files are the lock.

## Bandit

Bandit is the static check for SQL, shell, hardcoded passwords, and a few path and deserialization patterns. It is not installed by `requirements.txt` and it is not a CI job. Run it locally against the application modules when you add a query, a subprocess, or a secret:

```bash
python3 -m pip install bandit
bandit -r . -ll --exclude .venv,tests,docs,node_modules,static,.grok
```

`-ll` keeps the report to high severity. Triage a finding against the pairs in **[VULNERABILITIES.md](VULNERABILITIES.md)**. A test that deliberately calls `subprocess` is not a production finding; the exclude list leaves `tests/` out.

CodeQL runs as its own workflow. It does not replace a look at a new SQL string or a new `subprocess` call.

## Secrets

- `_build_config.py` in git is empty. A tag build may write Sentry and PostHog keys into the copy inside the PyInstaller tree. That file in the repository stays empty. An environment variable of the same name overrides the baked file for a source run. Do not commit a DSN or a project key.
- Do not commit `master.sqlite` or `root.sqlite`.
- `_report_failure` returns a fixed sentence. The exception text, which can contain a path, stays in the local log. A new error response follows that rule.
- Telemetry is off until the person opts in. Do not log a library path into a payload that can be sent.
- A hardcoded password or token (Bandit B105, B106) belongs in the environment or in the empty build-config file, not in source. Rotating a secret that was committed is a separate step from deleting the line.

## Path checks

Two different checks, both required when a caller supplies a name:

1. Reject a name that contains a slash, a backslash, or a null before joining.
2. Resolve the candidate and require the resolved path to stay inside the resolved base. A prefix compare without a trailing separator treats a sibling (`static-evil`) as inside `static`.

`LibraryHandler.send_file` realpaths the path and requires `candidate.startswith(root + os.sep)`. `files._contained` refuses a symlink and requires `resolved.parent == base`. Name validation and the resolve check are separate: a name with no slash can still be a symlink that points outside the folder.

`Path.is_relative_to` is only a containment check after both sides are resolved. Resolving a symlink is the point of the second check. Deleting either check while the other remains is a miss. Test them separately.

SQL identifiers such as a table name in `PRAGMA table_info` cannot be bound as parameters. The name has to be one the program chose, not a string from the request.

Subprocess calls pass an argument list (`["ps", "-p", str(int(pid)), "-o", "comm="]`). They do not use `shell=True`. Interpolating a path or a track title into a shell string is the bug Bandit reports as B602.

## Checklist

```
Dependencies:
- [ ] pip-audit is clean for requirements.txt and requirements-build.txt
- [ ] A new pin was added to the file the CI job actually reads

Code:
- [ ] Queries use placeholders; a SQL identifier is not taken from the request
- [ ] subprocess uses an argument list, not shell=True
- [ ] No new secret, DSN, or library path in source, in an error JSON body, or in telemetry
- [ ] A caller-supplied path is name-checked and resolve-checked, including the symlink case
- [ ] _build_config.py in the diff is still empty
```
