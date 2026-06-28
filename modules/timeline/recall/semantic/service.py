"""Semantic recall service: build embeddings for activity records and search.

Text for each record is normalised from the same fields the FTS index uses
(title + subtitle + body). Building is incremental and idempotent: re-running
only adds records not already in the index.

This service is optional and lazy. If the dependencies are missing it reports
``available == False`` and every operation is a no-op, so the rest of the app
is unaffected.
"""
from __future__ import annotations

import threading

from sqlalchemy import select, text as sql_text

from ..config import get_config
from ..logging_setup import get_logger
from ..db import get_database
from ..db.models import Application, BrowserVisit, FileEvent, Session
from .embedder import Embedder, dependencies_available
from .vector_index import VectorIndex

log = get_logger("semantic.service")


def semantic_available() -> bool:
    return dependencies_available()


def _normalise(title: str, subtitle: str, body: str) -> str:
    parts = [p for p in (title, subtitle, body) if p]
    return " — ".join(parts)[:512]


class SemanticService:
    def __init__(self):
        self.db = get_database()
        self._embedder: Embedder | None = None
        self._index: VectorIndex | None = None
        self._lock = threading.Lock()
        self._building = False
        self.available = dependencies_available()

    # --------------------------------------------------------------- helpers
    def _ensure(self) -> bool:
        if not self.available:
            return False
        if self._embedder is None:
            self._embedder = Embedder()
        if self._index is None:
            self._index = VectorIndex(dim=self._embedder.dim)
        return True

    def _iter_records(self):
        """Yield (kind, ref_id, normalised_text) for all searchable records."""
        with self.db.session() as orm:
            for s, a in orm.execute(
                select(Session, Application)
                .join(Application, Session.application_id == Application.id)
            ).all():
                yield ("session", s.id, _normalise(
                    s.window_title, a.display_name or a.name, a.name))
            for v in orm.execute(select(BrowserVisit)).scalars().all():
                yield ("browser", v.id, _normalise(v.title, v.domain, v.url))
            for f in orm.execute(select(FileEvent)).scalars().all():
                yield ("file", f.id, _normalise(f.filename, f.file_type, f.path))

    # ----------------------------------------------------------------- build
    def build(self, batch_size: int = 128) -> int:
        """Embed and index any records not yet present. Returns count added."""
        if not self._ensure():
            return 0
        with self._lock:
            if self._building:
                return 0
            self._building = True
        added = 0
        try:
            pending_keys: list[tuple[str, int]] = []
            pending_texts: list[str] = []

            def flush():
                nonlocal added
                if not pending_texts:
                    return
                vecs = self._embedder.encode(pending_texts)
                for (kind, ref_id), vec in zip(pending_keys, vecs):
                    self._index.add(kind, ref_id, vec)
                added += len(pending_texts)
                pending_keys.clear()
                pending_texts.clear()

            for kind, ref_id, text in self._iter_records():
                key = f"{kind}:{ref_id}"
                if key in self._index.key_to_pos:
                    continue
                if not text.strip():
                    continue
                pending_keys.append((kind, ref_id))
                pending_texts.append(text)
                if len(pending_texts) >= batch_size:
                    flush()
            flush()
            if added:
                self._index.save()
                log.info("Semantic build indexed %d new records (total %d)",
                         added, len(self._index))
        finally:
            self._building = False
        return added

    # ---------------------------------------------------------------- search
    def search(self, query: str, top_k: int = 25) -> list[dict]:
        """Return unified result dicts ranked by semantic similarity."""
        if not self._ensure() or not query.strip():
            return []
        if len(self._index) == 0:
            self.build()
        qvec = self._embedder.encode_one(query)
        hits = self._index.search(qvec, top_k=top_k)
        return self._hydrate(hits)

    def _hydrate(self, hits: list[tuple[str, int, float]]) -> list[dict]:
        from ..search.search_engine import _session_dict, _browser_dict, \
            _file_dict
        by_kind: dict[str, dict[int, float]] = {}
        for kind, ref_id, score in hits:
            by_kind.setdefault(kind, {})[ref_id] = score
        results: list[dict] = []
        with self.db.session() as orm:
            if "session" in by_kind:
                rows = orm.execute(
                    select(Session, Application)
                    .join(Application, Session.application_id == Application.id)
                    .where(Session.id.in_(list(by_kind["session"])))
                ).all()
                for s, a in rows:
                    d = _session_dict(s, a)
                    d["_score"] = by_kind["session"][s.id]
                    results.append(d)
            if "browser" in by_kind:
                rows = orm.execute(select(BrowserVisit).where(
                    BrowserVisit.id.in_(list(by_kind["browser"])))
                ).scalars().all()
                for v in rows:
                    d = _browser_dict(v)
                    d["_score"] = by_kind["browser"][v.id]
                    results.append(d)
            if "file" in by_kind:
                rows = orm.execute(select(FileEvent).where(
                    FileEvent.id.in_(list(by_kind["file"])))
                ).scalars().all()
                for f in rows:
                    d = _file_dict(f)
                    d["_score"] = by_kind["file"][f.id]
                    results.append(d)
        results.sort(key=lambda r: r.get("_score", 0.0), reverse=True)
        return results

    def reset(self) -> None:
        if self._ensure():
            self._index.reset()


_svc: SemanticService | None = None
_svc_lock = threading.Lock()


def get_semantic_service() -> SemanticService:
    global _svc
    with _svc_lock:
        if _svc is None:
            _svc = SemanticService()
        return _svc
