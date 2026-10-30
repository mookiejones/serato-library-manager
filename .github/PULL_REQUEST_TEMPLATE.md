## Summary

## Tests

<!-- Paste local results of every check below. -->

## Checklist

- [ ] Tests for this change are in this pull request; a bug fix has a test that fails before the fix
- [ ] Tests use only synthetic fixtures and cover relevant edge cases (Windows/macOS paths, symlinks/unmounted drives, Serato 4 vs 5, empty/missing library)
- [ ] Ran locally and pasted results: `npm ci`, `npx tsc --noEmit`, `npx eslint src`, `npm test`, `npm run build` (rebuilt `static/app.js` and `static/wizard.js` committed)
- [ ] `python3 -m unittest discover -s tests -t . -v` passes
- [ ] CI is green, including `tests (windows-latest, Python 3.12)`
- [ ] Docs for this change are in this pull request
- [ ] Anything not merged is marked PREVIEW
- [ ] `docs/architecture.md` is updated when behavior, the API, the layout, or the run path changes
- [ ] `CLAUDE.md` is updated when the run command or the layout summary changes
- [ ] `docs/github.md` is updated when a workflow, release step, or GitHub setting changes
- [ ] `PRIVACY.md` and the README are updated when sharing, local logs, or telemetry keys change
- [ ] `_build_config.py` stays empty, and no DSN or PostHog project key is in the diff
- [ ] No `master.sqlite`, `root.sqlite`, or other Serato library file is in the diff
