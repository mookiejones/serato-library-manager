"""Telemetry keys baked into a release build.

The release workflow overwrites this file from GitHub secrets before
PyInstaller runs. Empty strings keep each service off. This committed
copy must stay empty so a key never lands in git.
"""

SENTRY_DSN = ""
POSTHOG_KEY = ""
POSTHOG_HOST = ""
