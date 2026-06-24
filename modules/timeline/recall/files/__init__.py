"""File recall: harvest meaningful file activity from Windows-native signals."""
from .file_service import FileRecallService, scan_once

__all__ = ["FileRecallService", "scan_once"]
