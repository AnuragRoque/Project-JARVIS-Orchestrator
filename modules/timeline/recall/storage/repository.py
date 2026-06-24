"""Repository: the single gateway for reading/writing activity data.

Responsibilities:
* Upsert applications and record sessions.
* Record browser visits and file events.
* Keep the ``search_fts`` full-text index in sync with every write.
* Provide retention/cleanup and privacy deletion helpers.

The tracking, API, and UI layers all go through this class so the storage
schema stays encapsulated.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session as OrmSession

from ..config import get_config
from ..logging_setup import get_logger
from ..db import get_database
from ..db.models import (
    Application,
    BrowserVisit,
    FileEvent,
    Resource,
    Session,
    utcnow,
)

log = get_logger("storage.repository")


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc.split("@")[-1].split(":")[0].lower()
    except Exception:
        return ""


class Repository:
    def __init__(self):
        self.db = get_database()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ FTS
    def _fts_upsert(self, orm: OrmSession, kind: str, ref_id: int,
                    title: str, subtitle: str, body: str) -> None:
        # Delete any prior row for this (kind, ref_id) then insert fresh.
        orm.execute(
            text("DELETE FROM search_fts WHERE kind = :k AND ref_id = :r"),
            {"k": kind, "r": ref_id},
        )
        orm.execute(
            text(
                "INSERT INTO search_fts (kind, ref_id, title, subtitle, body) "
                "VALUES (:k, :r, :t, :s, :b)"
            ),
            {"k": kind, "r": ref_id, "t": title or "", "s": subtitle or "",
             "b": body or ""},
        )

    def _fts_delete(self, orm: OrmSession, kind: str, ref_id: int) -> None:
        orm.execute(
            text("DELETE FROM search_fts WHERE kind = :k AND ref_id = :r"),
            {"k": kind, "r": ref_id},
        )

    # ------------------------------------------------------------ Applications
    def upsert_application(self, orm: OrmSession, name: str,
                           exe_path: str | None) -> Application:
        name = (name or "unknown").lower()
        stmt = select(Application).where(
            Application.name == name,
            Application.exe_path == exe_path,
        )
        app = orm.execute(stmt).scalar_one_or_none()
        if app is None:
            display = os.path.splitext(name)[0].replace("_", " ").title()
            app = Application(
                name=name, exe_path=exe_path, display_name=display,
                first_seen=utcnow(), last_seen=utcnow(),
            )
            orm.add(app)
            orm.flush()
        return app

    # --------------------------------------------------------------- Sessions
    def record_session(self, *, process_name: str, exe_path: str | None,
                       window_title: str, pid: int | None,
                       start_time: datetime, end_time: datetime,
                       kind: str = "app") -> int | None:
        """Persist one completed session. Returns the session id (or None if
        skipped due to private mode / too short)."""
        cfg = get_config()
        if cfg.private_mode:
            return None
        duration = (end_time - start_time).total_seconds()
        if duration < cfg.min_session_seconds:
            return None

        with self._lock, self.db.session() as orm:
            app = self.upsert_application(orm, process_name, exe_path)
            app.last_seen = end_time
            app.total_seconds = (app.total_seconds or 0.0) + duration

            sess = Session(
                application_id=app.id,
                window_title=window_title or "",
                pid=pid,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                kind=kind,
            )
            orm.add(sess)
            orm.flush()
            self._fts_upsert(
                orm, "session", sess.id,
                title=window_title or app.display_name or app.name,
                subtitle=app.display_name or app.name,
                body=f"{app.name} {exe_path or ''}",
            )
            orm.commit()
            return sess.id

    # -------------------------------------------------------- Browser visits
    def record_browser_visit(self, *, url: str, title: str, browser: str,
                             tab_activated: datetime,
                             tab_closed: datetime | None = None,
                             source: str = "extension") -> int | None:
        cfg = get_config()
        if cfg.private_mode or not cfg.browser_tracking_enabled:
            return None
        domain = domain_of(url)
        if any(d and d in domain for d in cfg.excluded_domains):
            log.debug("Skipping excluded domain %s", domain)
            return None
        duration = 0.0
        if tab_closed:
            duration = max(0.0, (tab_closed - tab_activated).total_seconds())

        with self._lock, self.db.session() as orm:
            visit = BrowserVisit(
                url=url, title=title or "", domain=domain, browser=browser,
                tab_activated=tab_activated, tab_closed=tab_closed,
                duration_seconds=duration, source=source,
            )
            orm.add(visit)
            orm.flush()
            self._fts_upsert(
                orm, "browser", visit.id,
                title=title or url, subtitle=domain, body=url,
            )
            orm.commit()
            return visit.id

    # ------------------------------------------------------------ File events
    def record_file_event(self, *, path: str, application: str | None,
                          last_activity: datetime,
                          source: str = "recent") -> int | None:
        cfg = get_config()
        if cfg.private_mode:
            return None
        filename = os.path.basename(path)
        file_type = os.path.splitext(filename)[1].lstrip(".").lower()

        with self._lock, self.db.session() as orm:
            # Upsert by path.
            existing = orm.execute(
                select(FileEvent).where(FileEvent.path == path)
            ).scalar_one_or_none()
            if existing:
                existing.last_activity = max(existing.last_activity,
                                             last_activity)
                if application:
                    existing.application = application
                fid = existing.id
            else:
                fe = FileEvent(
                    path=path, filename=filename, file_type=file_type,
                    application=application, last_activity=last_activity,
                    source=source,
                )
                orm.add(fe)
                orm.flush()
                fid = fe.id
            self._fts_upsert(
                orm, "file", fid,
                title=filename, subtitle=file_type, body=path,
            )
            orm.commit()
            return fid

    # --------------------------------------------------------------- Queries
    def recent_sessions(self, *, since: datetime | None = None,
                         until: datetime | None = None,
                         limit: int = 200) -> list[dict]:
        with self.db.session() as orm:
            stmt = (
                select(Session, Application)
                .join(Application, Session.application_id == Application.id)
                .order_by(Session.start_time.desc())
                .limit(limit)
            )
            if since:
                stmt = stmt.where(Session.start_time >= since)
            if until:
                stmt = stmt.where(Session.start_time <= until)
            rows = orm.execute(stmt).all()
            return [self._session_to_dict(s, a) for s, a in rows]

    def _session_to_dict(self, s: Session, a: Application) -> dict:
        return {
            "kind": "session",
            "id": s.id,
            "title": s.window_title or a.display_name or a.name,
            "app": a.display_name or a.name,
            "process_name": a.name,
            "exe_path": a.exe_path,
            "window_title": s.window_title,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "duration_seconds": s.duration_seconds,
            "category": s.kind,
        }

    def application_stats(self, limit: int = 50) -> list[dict]:
        with self.db.session() as orm:
            stmt = (
                select(Application)
                .order_by(Application.total_seconds.desc())
                .limit(limit)
            )
            apps = orm.execute(stmt).scalars().all()
            return [
                {
                    "id": a.id,
                    "name": a.name,
                    "display_name": a.display_name or a.name,
                    "exe_path": a.exe_path,
                    "total_seconds": a.total_seconds,
                    "last_seen": a.last_seen,
                }
                for a in apps
            ]

    def recent_browser_visits(self, limit: int = 200) -> list[dict]:
        with self.db.session() as orm:
            rows = orm.execute(
                select(BrowserVisit)
                .order_by(BrowserVisit.tab_activated.desc())
                .limit(limit)
            ).scalars().all()
            return [
                {
                    "kind": "browser", "id": v.id, "title": v.title or v.url,
                    "url": v.url, "domain": v.domain, "browser": v.browser,
                    "start_time": v.tab_activated,
                    "duration_seconds": v.duration_seconds,
                }
                for v in rows
            ]

    def recent_files(self, limit: int = 200) -> list[dict]:
        with self.db.session() as orm:
            rows = orm.execute(
                select(FileEvent)
                .order_by(FileEvent.last_activity.desc())
                .limit(limit)
            ).scalars().all()
            return [
                {
                    "kind": "file", "id": f.id, "title": f.filename,
                    "path": f.path, "file_type": f.file_type,
                    "app": f.application, "start_time": f.last_activity,
                }
                for f in rows
            ]

    # ---------------------------------------------------------- Maintenance
    def apply_retention(self) -> int:
        """Delete records older than the configured retention window.
        Returns the number of source rows removed."""
        cfg = get_config()
        if cfg.retention_days <= 0:
            return 0
        cutoff = utcnow() - timedelta(days=cfg.retention_days)
        removed = 0
        with self._lock, self.db.session() as orm:
            removed += self._purge(orm, Session, Session.end_time, cutoff,
                                   "session")
            removed += self._purge(orm, BrowserVisit,
                                   BrowserVisit.tab_activated, cutoff, "browser")
            removed += self._purge(orm, FileEvent, FileEvent.last_activity,
                                   cutoff, "file")
            orm.commit()
        if removed:
            log.info("Retention purge removed %d records older than %s",
                     removed, cutoff.date())
        return removed

    def _purge(self, orm: OrmSession, model, time_col, cutoff, kind) -> int:
        ids = orm.execute(
            select(model.id).where(time_col < cutoff)
        ).scalars().all()
        for rid in ids:
            self._fts_delete(orm, kind, rid)
        if ids:
            orm.execute(delete(model).where(model.id.in_(ids)))
        return len(ids)

    def clear_all(self) -> None:
        with self._lock, self.db.session() as orm:
            for model in (Session, BrowserVisit, FileEvent, Resource,
                          Application):
                orm.execute(delete(model))
            orm.execute(text("DELETE FROM search_fts"))
            orm.commit()
        log.warning("All activity history cleared by user request")

    def delete_records(self, kind: str, ids: list[int]) -> int:
        model = {
            "session": Session, "browser": BrowserVisit,
            "file": FileEvent, "resource": Resource,
        }.get(kind)
        if not model or not ids:
            return 0
        with self._lock, self.db.session() as orm:
            for rid in ids:
                self._fts_delete(orm, kind, rid)
            orm.execute(delete(model).where(model.id.in_(ids)))
            orm.commit()
        return len(ids)

    def counts(self) -> dict:
        with self.db.session() as orm:
            return {
                "applications": orm.scalar(select(func.count(Application.id))),
                "sessions": orm.scalar(select(func.count(Session.id))),
                "browser_visits": orm.scalar(select(func.count(BrowserVisit.id))),
                "file_events": orm.scalar(select(func.count(FileEvent.id))),
            }


_repo: Repository | None = None
_repo_lock = threading.Lock()


def get_repository() -> Repository:
    global _repo
    with _repo_lock:
        if _repo is None:
            _repo = Repository()
        return _repo
