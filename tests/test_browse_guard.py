"""Browse guards for a shortcut that sits near the top of the disk.

The deep-shortcut check allows an alias one or two components below the
drive. A shortcut inside a music root is still refused. These tests do
not open a live Serato library.
"""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import files
import library
import music_roots
from tests.fixture import TempLibrary


class ShallowShortcutTests(unittest.TestCase):
    """A shortcut under a music root is refused even when it is not deep."""

    def test_a_shallow_shortcut_under_the_root_is_refused(self) -> None:
        """Refuse a shortcut two components below the disk, and open a real folder.

        ``/tmp/<name>`` is shallow enough that the top-of-disk alias check
        allows it. The music-root check still refuses the shortcut and
        still opens a real folder at that depth.

        Returns:
            None. The test fails if the link is listed or the real folder is refused.
        """
        with TempLibrary() as temp:
            secret = temp.root / "secret"
            secret.mkdir()
            (secret / "hidden.mp3").write_bytes(b"x")
            anchor = _shallow_anchor()
            if anchor is None:
                self.skipTest("no shallow folder is available")
            token = uuid.uuid4().hex
            link = anchor / f"serato-shallow-{token}"
            real = anchor / f"serato-real-{token}"
            try:
                real.mkdir()
            except OSError:
                self.skipTest("cannot create a shallow folder")
            root_path = str(anchor.resolve())
            roots = [
                {
                    "name": "Temp · /",
                    "path": root_path,
                    "kind": "folder",
                    "missing": False,
                }
            ]
            try:
                link.symlink_to(secret, target_is_directory=True)
            except OSError:
                real.rmdir()
                self.skipTest("symlinks are not available")
            try:
                with mock.patch.object(music_roots, "music_roots", return_value=roots):
                    files.invalidate_browse_cache()
                    with self.assertRaises(library.LibraryError) as caught:
                        files.list_directory(str(link))
                    self.assertEqual(caught.exception.message, "Shortcuts are left alone.")
                    opened = files.list_directory(str(real))
                self.assertEqual(opened["path"], str(real.resolve()))
                self.assertEqual(opened["entries"], [])
                self.assertEqual(opened["parent"], str(real.resolve().parent))
                self.assertEqual(opened["breadcrumb"][0]["path"], root_path)
            finally:
                link.unlink(missing_ok=True)
                real.rmdir()


def _shallow_anchor() -> Path | None:
    """Return a directory one or two components below the drive.

    The deep-shortcut check allows a shortcut at that depth. ``/tmp`` is
    that directory on Linux. Windows uses the drive root when it can be
    used as a parent.

    Returns:
        The directory, or None when neither candidate exists.
    """
    if Path("/tmp").is_dir():
        return Path("/tmp")
    anchor = Path(Path.cwd().anchor)
    if anchor.is_dir() and anchor != Path("/"):
        return anchor
    return None


if __name__ == "__main__":
    unittest.main()
