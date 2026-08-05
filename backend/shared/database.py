from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from shared.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


_settings = get_settings()
if _settings.is_cosmos_only_mode():
    engine = None
    SessionLocal = None
else:
    engine = _build_engine()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("Persistencia SQL deshabilitada en modo cosmos_only")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
