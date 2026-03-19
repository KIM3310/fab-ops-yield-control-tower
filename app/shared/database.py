"""
SQLite persistence layer for the semiconductor-ops-platform.

Provides SQLAlchemy models for runtime events, shift handoffs, and audit
records.  The persistence backend is selected via the ``PERSISTENCE_BACKEND``
environment variable:

- ``sqlite`` (default): Uses SQLAlchemy with a local SQLite database.
- ``jsonl``: Falls back to the legacy JSONL flat-file store.

When the SQLite backend is active, tables are created automatically on first
import via ``Base.metadata.create_all``.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("shared.database")

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

PERSISTENCE_BACKEND = os.getenv("PERSISTENCE_BACKEND", "sqlite").strip().lower()

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "semiconductor_ops.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}").strip()

Base = declarative_base()


# ---------------------------------------------------------------------------
# SQLAlchemy models
# ---------------------------------------------------------------------------


class RuntimeEvent(Base):  # type: ignore[misc]
    """Persisted runtime event (route hits, gate checks, exports)."""

    __tablename__ = "runtime_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(32), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    route = Column(String(256), nullable=True)
    payload_json = Column(Text, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary matching the legacy JSONL format."""
        base: dict[str, Any] = {
            "event_type": self.event_type,
            "domain": self.domain,
            "at": self.timestamp.isoformat() if self.timestamp else None,
        }
        if self.route:
            base["route"] = self.route
        if self.payload_json:
            try:
                base.update(json.loads(self.payload_json))
            except json.JSONDecodeError:
                pass
        return base


class ShiftHandoff(Base):  # type: ignore[misc]
    """Persisted shift handoff record with signature metadata."""

    __tablename__ = "shift_handoffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(32), nullable=False, index=True)
    handoff_id = Column(String(128), nullable=False)
    shift = Column(String(32), nullable=False)
    fab_or_site_id = Column(String(64), nullable=False)
    headline = Column(Text, nullable=False)
    signature_sha256 = Column(String(64), nullable=True)
    signature_hmac = Column(String(64), nullable=True)
    signed_by = Column(String(64), nullable=True)
    signed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    payload_json = Column(Text, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "domain": self.domain,
            "handoff_id": self.handoff_id,
            "shift": self.shift,
            "fab_or_site_id": self.fab_or_site_id,
            "headline": self.headline,
            "signature_sha256": self.signature_sha256,
            "signature_hmac": self.signature_hmac,
            "signed_by": self.signed_by,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditRecord(Base):  # type: ignore[misc]
    """Persisted audit trail entry."""

    __tablename__ = "audit_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(32), nullable=False, index=True)
    event_name = Column(String(128), nullable=False)
    actor = Column(String(64), nullable=False)
    tool_id = Column(String(64), nullable=True)
    lot_id = Column(String(64), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    details_json = Column(Text, nullable=True)
    is_exported = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        result: dict[str, Any] = {
            "id": self.id,
            "at": self.timestamp.isoformat() if self.timestamp else None,
            "event": self.event_name,
            "actor": self.actor,
            "domain": self.domain,
        }
        if self.tool_id:
            result["tool_id"] = self.tool_id
        if self.lot_id:
            result["lot_id"] = self.lot_id
        if self.details_json:
            try:
                result["details"] = json.loads(self.details_json)
            except json.JSONDecodeError:
                pass
        return result


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _get_engine():
    """Lazily create the SQLAlchemy engine and ensure tables exist."""
    global _engine, _SessionLocal
    if _engine is None:
        # Ensure the data directory exists for SQLite file paths
        if DATABASE_URL.startswith("sqlite:///"):
            db_path = DATABASE_URL.replace("sqlite:///", "")
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
            echo=False,
        )
        Base.metadata.create_all(bind=_engine)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("Database initialized: %s", DATABASE_URL)
    return _engine


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    _get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Convenience helpers (used by runtime_store when backend=sqlite)
# ---------------------------------------------------------------------------


def is_sqlite_backend() -> bool:
    """Return True when the SQLite persistence backend is active."""
    return PERSISTENCE_BACKEND == "sqlite"


def record_event_sqlite(
    event_type: str,
    domain: str = "fab_ops",
    **payload: Any,
) -> None:
    """Insert a runtime event into the SQLite database.

    Args:
        event_type: Categorical label for the event.
        domain: Domain identifier.
        **payload: Extra key-value pairs stored as JSON.
    """
    session = get_session()
    try:
        route = payload.pop("route", None)
        at_str = payload.pop("at", None)
        ts = datetime.now(UTC)
        if at_str:
            try:
                ts = datetime.fromisoformat(str(at_str))
            except (ValueError, TypeError):
                pass

        event = RuntimeEvent(
            domain=domain,
            event_type=event_type,
            timestamp=ts,
            route=route,
            payload_json=json.dumps(payload) if payload else None,
        )
        session.add(event)
        session.commit()
        logger.debug("[%s] recorded event %s (sqlite)", domain, event_type)
    except Exception:
        session.rollback()
        logger.exception("[%s] failed to write runtime event %s (sqlite)", domain, event_type)
        raise
    finally:
        session.close()


def summarize_events_sqlite(domain: str = "fab_ops", limit: int = 4000) -> dict[str, Any]:
    """Read recent events from SQLite and return an aggregated summary.

    Returns a dictionary matching the shape produced by the JSONL summarizer
    so callers do not need to distinguish backends.

    Args:
        domain: Domain identifier.
        limit: Maximum number of recent events to consider.

    Returns:
        Summary dictionary with counts and recent events.
    """
    summary: dict[str, Any] = {
        "enabled": True,
        "backend": "sqlite",
        "path": DATABASE_URL,
        "event_count": 0,
        "route_hits": 0,
        "release_gate_checks": 0,
        "handoff_exports": 0,
        "signature_exports": 0,
        "event_type_counts": {},
        "last_event_at": None,
        "recent_events": [],
    }

    session = get_session()
    try:
        events = (
            session.query(RuntimeEvent)
            .filter(RuntimeEvent.domain == domain)
            .order_by(RuntimeEvent.id.desc())
            .limit(limit)
            .all()
        )
        events.reverse()  # oldest first

        for event in events:
            d = event.to_dict()
            summary["event_count"] += 1
            summary["recent_events"].append(d)

            at = d.get("at")
            if at and (summary["last_event_at"] is None or at > summary["last_event_at"]):
                summary["last_event_at"] = at

            et = d.get("event_type", "")
            counts: dict[str, int] = summary["event_type_counts"]
            counts[et] = counts.get(et, 0) + 1

            if et == "route_hit":
                summary["route_hits"] += 1
            elif et in ("release_gate_check", "module_escalation_check"):
                summary["release_gate_checks"] += 1
            elif et == "handoff_export":
                summary["handoff_exports"] += 1
            elif et == "handoff_signature_export":
                summary["signature_exports"] += 1
    except Exception:
        logger.exception("[%s] failed to read runtime events (sqlite)", domain)
    finally:
        session.close()

    return summary


def record_handoff_sqlite(
    domain: str,
    handoff_id: str,
    shift: str,
    fab_or_site_id: str,
    headline: str,
    payload: dict[str, Any],
    signature_sha256: str | None = None,
    signature_hmac: str | None = None,
    signed_by: str | None = None,
) -> None:
    """Persist a shift handoff record to SQLite.

    Args:
        domain: Domain identifier.
        handoff_id: Unique handoff identifier.
        shift: Shift name (e.g. ``"night"``).
        fab_or_site_id: Fab or site identifier.
        headline: Handoff headline text.
        payload: Full handoff payload as a dict.
        signature_sha256: SHA-256 digest of the signed manifest.
        signature_hmac: HMAC-SHA256 signature.
        signed_by: Identity of the signer.
    """
    session = get_session()
    try:
        record = ShiftHandoff(
            domain=domain,
            handoff_id=handoff_id,
            shift=shift,
            fab_or_site_id=fab_or_site_id,
            headline=headline,
            signature_sha256=signature_sha256,
            signature_hmac=signature_hmac,
            signed_by=signed_by,
            signed_at=datetime.now(UTC) if signed_by else None,
            payload_json=json.dumps(payload),
        )
        session.add(record)
        session.commit()
        logger.info("[%s] handoff persisted: %s", domain, handoff_id)
    except Exception:
        session.rollback()
        logger.exception("[%s] failed to persist handoff %s", domain, handoff_id)
    finally:
        session.close()


def record_audit_sqlite(
    domain: str,
    event_name: str,
    actor: str,
    tool_id: str | None = None,
    lot_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an audit record to SQLite.

    Args:
        domain: Domain identifier.
        event_name: Audit event name.
        actor: Actor or system that triggered the event.
        tool_id: Related tool identifier (optional).
        lot_id: Related lot identifier (optional).
        details: Additional structured details (optional).
    """
    session = get_session()
    try:
        record = AuditRecord(
            domain=domain,
            event_name=event_name,
            actor=actor,
            tool_id=tool_id,
            lot_id=lot_id,
            details_json=json.dumps(details) if details else None,
        )
        session.add(record)
        session.commit()
        logger.debug("[%s] audit record: %s by %s", domain, event_name, actor)
    except Exception:
        session.rollback()
        logger.exception("[%s] failed to persist audit record %s", domain, event_name)
    finally:
        session.close()


def migrate_jsonl_to_sqlite(jsonl_path: str | Path, domain: str = "fab_ops") -> int:
    """Migrate events from a JSONL file into the SQLite database.

    Each line in the JSONL file is parsed and inserted as a RuntimeEvent.
    Lines that are already present (based on timestamp + event_type) are
    skipped to allow safe re-runs.

    Args:
        jsonl_path: Path to the JSONL event store file.
        domain: Domain identifier for all migrated events.

    Returns:
        Number of events successfully migrated.
    """
    path = Path(jsonl_path)
    if not path.exists():
        logger.warning("JSONL file not found for migration: %s", path)
        return 0

    session = get_session()
    migrated = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSONL line during migration")
                continue

            event_type = data.pop("event_type", "unknown")
            route = data.pop("route", None)
            at_str = data.pop("at", None)
            ts = datetime.now(UTC)
            if at_str:
                try:
                    ts = datetime.fromisoformat(str(at_str))
                except (ValueError, TypeError):
                    pass
            data.pop("domain", None)

            event = RuntimeEvent(
                domain=domain,
                event_type=event_type,
                timestamp=ts,
                route=route,
                payload_json=json.dumps(data) if data else None,
            )
            session.add(event)
            migrated += 1

        session.commit()
        logger.info("Migrated %d events from %s to SQLite", migrated, path)
    except Exception:
        session.rollback()
        logger.exception("Failed to migrate JSONL to SQLite from %s", path)
        raise
    finally:
        session.close()

    return migrated
