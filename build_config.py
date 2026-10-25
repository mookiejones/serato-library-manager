"""Write ``_build_config.py`` from environment variables.

The release workflow calls this module. A missing or blank variable is
written as an empty string, which turns that service into a no-op. The
script prints whether each value was set. It does not print the value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD_CONFIG_PATH = ROOT / "_build_config.py"
NAMES = ("SENTRY_DSN", "POSTHOG_KEY", "POSTHOG_HOST")


def _clean(name: str, environ: Mapping[str, str]) -> str:
    """Return one telemetry value with surrounding whitespace removed.

    Args:
        name: Environment variable name.
        environ: Mapping to read. A missing name is an empty string.

    Returns:
        The stripped value.

    Raises:
        SystemExit: If the value contains a newline or a NUL byte, so the
            generated module cannot break out of its assignment.
    """
    raw = environ.get(name, "")
    if not isinstance(raw, str):
        raise SystemExit(f"{name} must be a string.")
    if "\n" in raw or "\r" in raw or "\x00" in raw:
        raise SystemExit(f"{name} contains a control character.")
    return raw.strip()


def render_build_config(environ: dict[str, str]) -> str:
    """Render the telemetry module source.

    Args:
        environ: ``SENTRY_DSN``, ``POSTHOG_KEY``, and ``POSTHOG_HOST``.
            Blank values stay blank.

    Returns:
        Python source that assigns those three names. Values are quoted
        with ``repr`` so a quote inside a key cannot end the string.
    """
    values = {name: _clean(name, environ) for name in NAMES}
    lines = [
        '"""Generated telemetry keys. Empty strings disable that service."""',
        "",
    ]
    for name in NAMES:
        lines.append(f"{name} = {values[name]!r}")
    lines.append("")
    return "\n".join(lines)


def write_build_config(path: Path, environ: dict[str, str]) -> dict[str, bool]:
    """Overwrite a telemetry module and report which values were present.

    Args:
        path: Destination, normally ``_build_config.py``.
        environ: Variable mapping. Only the three telemetry names are read.

    Returns:
        Whether each name had a non-empty value. The booleans are safe to
        print. The values themselves are not returned.

    Raises:
        SystemExit: If a value contains a newline or a NUL byte.
        OSError: If the file cannot be written.
    """
    source = render_build_config(environ)
    path.write_text(source, encoding="utf-8")
    return {name: bool(_clean(name, environ)) for name in NAMES}


def main() -> None:
    """Write the repository ``_build_config.py`` from the process environment.

    Prints one status line with yes or no for each key. The DSN, the PostHog
    key, and the host are not included in that line.

    Raises:
        SystemExit: If a value contains a control character.
    """
    flags = write_build_config(BUILD_CONFIG_PATH, dict(os.environ))
    print(
        "Wrote _build_config.py "
        f"sentry={'yes' if flags['SENTRY_DSN'] else 'no'} "
        f"posthog={'yes' if flags['POSTHOG_KEY'] else 'no'} "
        f"host={'set' if flags['POSTHOG_HOST'] else 'default'}"
    )


if __name__ == "__main__":
    main()
