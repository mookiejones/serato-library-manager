# Privacy

Sharing is off until you turn it on. The first time the page opens it asks:

> Share anonymous usage stats and crash reports?

**Don't share** is selected by default. Closing the prompt or pressing Esc saves that choice. Settings in the sidebar can change it later. Nothing is sent before you choose Share, and nothing is sent while the choice stays off.

## What can be sent

A report leaves the machine only after you opt in, and only when this copy of the app has a key for that service.

Usage counts go to PostHog. The events are `app_opened`, `library_scanned`, `crate_created`, `backup_made`, `tags_read`, `files_changed`, `related_link_saved`, `related_link_removed`, `related_crate_written`, and `duplicates_merged`. `library_scanned` includes a track-count range such as `100-499`, not the exact number. `files_changed` includes a file-count range, a change type (`rename`, `move`, `move_folder`, `replace`, or `delete`), and, for a replacement, whether cue points were copied (`copied`, `kept`, `skipped`, `unsupported`, or `failed`). It does not include a path or a file name. `related_link_saved` includes `link_direction` set to `one_way` or `two_way`. It does not include a note, a rating, a title, or a path. `duplicates_merged` is only the fact that a duplicate merge finished. It does not include how many tracks moved, which file was kept, or any title or path. Each event includes `app` set to `serato-library-manager`, the app version (`1.1.0`), and the operating system. Crash reports use that same version as the Sentry release. The PostHog library also attaches its own Python and library version fields. GeoIP is disabled.

Crash reports go to Sentry. A report is the exception type and a stack trace. The tag `app` is `serato-library-manager`. A file path in that report is replaced with `[path]`. A Python file is kept as its name only, such as `server.py`. The machine hostname is not sent. Request bodies and local variables are not sent.

The install is identified by a random id created when you save a choice. That id is not your name, and it is not a Serato account.

## What is never sent

Track titles, artists, crate names, file paths, playlist text, and the rows in `master.sqlite` are not usage properties. The page does not load a PostHog or Sentry script. Reports leave from the Python process only.

A missing `SENTRY_DSN` keeps crash reports off even after you opt in. A missing `POSTHOG_KEY` keeps usage counts off. `POSTHOG_HOST` defaults to `https://us.i.posthog.com` when a project key is set and no host is configured.

## Where the choice is stored

| System | Settings | Logs |
|--------|----------|------|
| macOS | `~/Library/Application Support/Serato Library/settings.json` and `related.sqlite` | `~/Library/Logs/Serato Library/` |
| Windows | `%APPDATA%\Serato Library\settings.json` and `related.sqlite` | `%LOCALAPPDATA%\Serato Library\Logs\` |
| Linux | `$XDG_CONFIG_HOME/serato-library/settings.json` and `related.sqlite`, or `~/.config/serato-library/` | `$XDG_STATE_HOME/serato-library/logs`, or `~/.local/state/serato-library/logs` |

`related.sqlite` stores which tracks you marked as going well together, including file paths, titles, artists, lengths, notes, and ratings. That file stays on this machine. It is not a usage report. The schema is in [docs/related-tracks.md](docs/related-tracks.md).

The log file is `serato-library.log`. It rotates at 1 MiB and keeps three older files. Logs stay on this machine. They can include the path of the library database. They are not uploaded. Settings has **Open logs folder** and **Copy logs**.

## Release builds

A tagged release writes `SENTRY_DSN`, `POSTHOG_KEY`, and `POSTHOG_HOST` from GitHub Actions secrets into `_build_config.py` before the app is frozen. A manual run of that workflow does not. An empty secret leaves that service off. The copy of `_build_config.py` in git is empty, and a build from source uses that empty file. Do not commit a filled-in key file.

Those values are client keys. They end up inside the unsigned build. They do not grant access to the Serato library. For a local run, set the same variable names in the environment. An environment value overrides the baked file.
