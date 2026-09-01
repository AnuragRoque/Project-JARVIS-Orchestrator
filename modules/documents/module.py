"""Documents module: find files on disk and read their contents.

- ``find_files``   — locate files by name/type in the real folders (Downloads,
  Documents, Desktop, or a given folder), newest first.
- ``read_document`` — extract text from a file (text / PDF / .docx) so JARVIS can
  summarise or answer questions about it. Accepts a full path, or a name/query it
  resolves against those folders.

Both are read-only, so they never trigger a permission prompt.
"""
from __future__ import annotations

import os
from datetime import datetime

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool
from .finder import find_files
from .reader import read_document

log = get_logger("module.documents")

FIND_FILES_SPEC = {
    "type": "function",
    "function": {
        "name": "find_files",
        "description": (
            "Find files on disk by name and/or type, newest first. Searches the "
            "user's Downloads, Documents and Desktop by default, or a named folder "
            "('downloads', 'documents', 'desktop') / an absolute path. Use for "
            "'find my resume in downloads', 'latest invoice', 'the pdf about X'. "
            "Each result has a 'path' — open one with open_file(path) or read one "
            "with read_document(path). Do NOT use recall_open for these."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words in the file name."},
                "folder": {"type": "string",
                           "description": "'downloads' | 'documents' | 'desktop' | a path."},
                "ext": {"type": "string",
                        "description": "Restrict by extension(s), e.g. 'pdf' or 'pdf,docx'."},
                "limit": {"type": "integer", "description": "Max results (default 15)."},
            },
        },
    },
}

OPEN_FILE_SPEC = {
    "type": "function",
    "function": {
        "name": "open_file",
        "description": (
            "Open a file or folder in its default app by its PATH (opens a PDF in "
            "the PDF viewer, a doc in Word, a folder in Explorer). Use this to open "
            "a file the user picked from find_files — pass that file's 'path'. Do "
            "NOT use recall_open for find_files results (recall_open is only for "
            "recall_search / browser_recall / list_recent_files)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to the file/folder."},
            },
            "required": ["path"],
        },
    },
}

READ_DOCUMENT_SPEC = {
    "type": "function",
    "function": {
        "name": "read_document",
        "description": (
            "Read the text contents of a file so you can summarise it or answer "
            "questions about it. Supports plain text/code/csv/json, PDF, and Word "
            ".docx. Give a full 'path', or a 'name' to look up (e.g. 'resume.pdf'). "
            "Use for 'read/summarise this file', 'what does my resume say'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to the file."},
                "name": {"type": "string",
                         "description": "File name/keywords to locate if no path is given."},
                "folder": {"type": "string",
                           "description": "Where to look for 'name' (default: common folders)."},
                "max_chars": {"type": "integer",
                              "description": "Max characters to return (default 8000)."},
            },
        },
    },
}


class DocumentsModule(Module):
    id = "documents"
    name = "Documents"
    version = "0.1.0"

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def tools(self) -> list[Tool]:
        return [
            Tool(FIND_FILES_SPEC, self.find_files, "read_only"),
            Tool(OPEN_FILE_SPEC, self.open_file, "safe_action"),
            Tool(READ_DOCUMENT_SPEC, self.read_document, "read_only"),
        ]

    def open_file(self, path: str = "") -> dict:
        target = (path or "").strip().strip('"')
        if not target or not os.path.exists(target):
            return {"ok": False,
                    "error": f"No such file: {path!r}. Use find_files to get a valid path."}
        try:
            os.startfile(target)  # default app / Explorer for folders
        except Exception as exc:
            log.exception("open_file failed")
            return {"ok": False, "error": f"Couldn't open it: {exc}"}
        log_event("documents", f"open: {os.path.basename(target)}",
                  module="documents", detail=target, decision="opened")
        return {"ok": True, "opened": os.path.basename(target), "path": target,
                "message": f"Opened {os.path.basename(target)}."}

    # ------------------------------------------------------------- handlers
    def find_files(self, query: str = "", folder: str | None = None,
                   ext: str | None = None, limit: int = 15) -> dict:
        try:
            hits = find_files(query=query, folder=folder, ext=ext, limit=limit)
        except Exception as exc:
            log.exception("find_files failed")
            return {"ok": False, "error": f"Search failed: {exc}"}
        items = [{
            "index": i, "name": h["name"], "path": h["path"],
            "size_kb": round(h["size"] / 1024, 1),
            "modified": _when(h["modified"]),
        } for i, h in enumerate(hits, 1)]
        out = {"ok": True, "count": len(items), "results": items}
        if not items:
            out["note"] = "No matching files found. Tell the user; don't guess a path."
        return out

    def read_document(self, path: str = "", name: str | None = None,
                      folder: str | None = None, max_chars: int = 8000) -> dict:
        target = (path or "").strip()
        if not target or not os.path.isfile(target):
            # Resolve a name/keywords against the real folders.
            query = name or (target if not os.path.sep in target else "")
            if query:
                hits = find_files(query=query, folder=folder, limit=1)
                if hits:
                    target = hits[0]["path"]
        if not target or not os.path.isfile(target):
            return {"ok": False,
                    "error": f"I couldn't find that file "
                             f"({path or name!r}). Try find_files first."}
        result = read_document(target, max_chars=int(max_chars or 8000))
        log_event("documents", f"read: {os.path.basename(target)}",
                  module="documents", detail=target,
                  decision="ok" if result.get("ok") else "failed")
        return result


def _when(dt: datetime) -> str:
    return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")


def get_module() -> Module:
    return DocumentsModule()
