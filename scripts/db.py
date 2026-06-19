"""Database engine / session helpers."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import config
from .models import AuditLog, Base

_engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def get_engine():
    return _engine


def init_db(drop: bool = False) -> None:
    """Create all tables (optionally dropping existing ones first)."""
    if drop:
        Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)


@contextmanager
def session_scope():
    """Transactional session context manager."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def log_audit(session, action: str, entity_type: str | None = None,
              entity_id: int | None = None, details: dict | None = None,
              actor: str = "system") -> None:
    """Append an audit-trail entry within the given session."""
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )
