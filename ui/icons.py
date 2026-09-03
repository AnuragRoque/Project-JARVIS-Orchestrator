"""Lucide icons rendered to Qt pixmaps/icons — no asset files, no new deps.

Lucide (https://lucide.dev, MIT) icons are simple stroked SVGs on a 24×24
viewBox. We keep just the inner markup for the few icons the UI needs and wrap
it at render time with the stroke/colour we want, then rasterise through
``QSvgRenderer`` (part of PyQt6) at high resolution for a crisp result on any DPI.

Usage::

    btn.setIcon(lucide_icon("mic", color="#ffffff", size=24))
    btn.setIconSize(QSize(24, 24))
    label.setPixmap(lucide_pixmap("shield-check", color="#8a93a3", size=14))

Recolour by passing a different ``color``; Qt does not tint an existing QIcon,
so ask for the colour you want up front (e.g. a brighter shade for hover).
"""
from __future__ import annotations

import base64
from functools import lru_cache

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Inner SVG markup for each icon (verbatim from Lucide, 24×24 viewBox).
_ICONS: dict[str, str] = {
    # microphone
    "mic": (
        '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
        '<line x1="12" y1="19" x2="12" y2="22"/>'
    ),
    # microphone with a slash (muted / stop listening)
    "mic-off": (
        '<line x1="2" y1="2" x2="22" y2="22"/>'
        '<path d="M18.89 13.23A7.12 7.12 0 0 0 19 12v-2"/>'
        '<path d="M5 10v2a7 7 0 0 0 12 5"/>'
        '<path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/>'
        '<path d="M9 9v3a3 3 0 0 0 5.12 2.12"/>'
        '<line x1="12" y1="19" x2="12" y2="22"/>'
    ),
    # collapse / minimise
    "minus": '<path d="M5 12h14"/>',
    # close
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    # open full window (expand arrows)
    "maximize-2": (
        '<polyline points="15 3 21 3 21 9"/>'
        '<polyline points="9 21 3 21 3 15"/>'
        '<line x1="21" y1="3" x2="14" y2="10"/>'
        '<line x1="3" y1="21" x2="10" y2="14"/>'
    ),
    # permission shield
    "shield-check": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6'
        'a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5'
        'a1 1 0 0 1 1 1z"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    # send (paper plane)
    "send": (
        '<line x1="22" y1="2" x2="11" y2="13"/>'
        '<polygon points="22 2 15 22 11 13 2 9 22 2"/>'
    ),
    # stop (filled-look square outline)
    "square": '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    # warning
    "alert-triangle": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
    # reminder bell
    "bell": (
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
    ),
    # disclosure chevrons (for expandable step rows)
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    # live audio (waveform) — the hands-free "Live" button
    "audio-lines": (
        '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/>'
        '<path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>'
    ),
    # robot — "open the floating orb"
    "bot": (
        '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/>'
        '<path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>'
    ),
    # person — the "You" role marker
    "user": (
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>'
        '<circle cx="12" cy="7" r="4"/>'
    ),
    # keyboard — the "type instead" input toggle
    "keyboard": (
        '<rect width="20" height="16" x="2" y="4" rx="2"/>'
        '<path d="M6 8h.01"/><path d="M10 8h.01"/><path d="M14 8h.01"/><path d="M18 8h.01"/>'
        '<path d="M8 12h.01"/><path d="M12 12h.01"/><path d="M16 12h.01"/><path d="M7 16h10"/>'
    ),
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_OVERSAMPLE = 3  # rasterise at 3× logical size, then flag the DPR → crisp everywhere


def _svg_bytes(name: str, color: str, stroke: float) -> QByteArray:
    body = _ICONS.get(name)
    if body is None:
        raise KeyError(f"Unknown lucide icon '{name}'. Add its markup to icons.py.")
    return QByteArray(_SVG.format(color=color, stroke=stroke, body=body).encode("utf-8"))


@lru_cache(maxsize=128)
def lucide_pixmap(name: str, color: str = "#e6e9ef", size: int = 18,
                  stroke: float = 2.0) -> QPixmap:
    """Return a transparent QPixmap of the icon, crisp at the given logical size."""
    px = max(1, int(round(size * _OVERSAMPLE)))
    renderer = QSvgRenderer(_svg_bytes(name, color, stroke))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    pm.setDevicePixelRatio(_OVERSAMPLE)
    return pm


@lru_cache(maxsize=128)
def lucide_icon(name: str, color: str = "#e6e9ef", size: int = 18,
                stroke: float = 2.0) -> QIcon:
    """Return a QIcon for the named Lucide icon in the requested colour/size."""
    return QIcon(lucide_pixmap(name, color, size, stroke))


@lru_cache(maxsize=128)
def lucide_data_uri(name: str, color: str = "#e6e9ef", size: int = 14,
                    stroke: float = 2.0) -> str:
    """A ``data:image/png;base64,…`` URI for inline use in QLabel rich text."""
    pm = lucide_pixmap(name, color, size, stroke)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
    buf.close()
    return f"data:image/png;base64,{b64}"
