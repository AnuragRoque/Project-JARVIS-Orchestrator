"""Back-compat shim — the styling system now lives in :mod:`jarvis.ui.theme`.

Surfaces should call the theme builders directly and re-apply on
``theme_manager.changed`` so they follow the live global theme. These names are
kept only so older imports keep working.
"""
from jarvis.ui.theme import (  # noqa: F401
    app_qss,
    glass_qss,
    placeholder_qss,
    terminal_qss,
    theme_manager,
    toast_qss,
)

# Legacy accent snapshots (prefer ``theme_manager.palette().accent`` for live values).
ACCENT = theme_manager.palette().accent
ACCENT_2 = theme_manager.palette().accent2
