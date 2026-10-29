"""Release identity baked by the packaging workflow.

The release job overwrites this file from the tag before PyInstaller runs.
Empty strings mean a development checkout. ``version_info`` then uses
``git describe``, or ``0.0.0+dev`` when git is missing. This committed
copy must stay empty so a hand-edited version cannot drift from the tag.
"""

VERSION = ""
COMMIT = ""
SOURCE = ""
