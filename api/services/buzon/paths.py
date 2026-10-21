"""Buzón path constants — single source of truth for the package.

These are STRUCTURAL constants tied to the buzón document-format convention,
not deployment parameters.  They must match the exact ``path`` values that the
scaffold writes into the ``documents`` table (always with a trailing slash).

Why here and not in ``config.py`` / ``.env``?
----------------------------------------------
``config.py`` / ``.env`` carry deployment-time settings (database URL,
service mode, credentials, ports).  The buzón paths are part of the *data
model*: changing them would require a database migration, not a config change.
They are analogous to the ``/wiki/`` prefix used in ``startup/hosted.py`` for
the scaffold — a structural invariant of the buzón format, not a knob the
operator tunes per environment.  A single domain constant shared across the
package is the correct and minimal solution.

Usage
-----
Import from the package root::

    from services.buzon import BUZON_PATH, BUZON_ARCHIVO_PATH
"""

# Path where active buzón documents live (exact ``path`` column value).
# The trailing slash means an exact-match query on this value naturally
# excludes ``/wiki/buzon/archivo/`` and any future subfolders.
BUZON_PATH = "/wiki/buzon/"

# Path where archived buzón documents live.
# Reserved for BZ-005/006/007 archive logic.
BUZON_ARCHIVO_PATH = "/wiki/buzon/archivo/"
