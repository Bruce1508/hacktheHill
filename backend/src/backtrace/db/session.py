from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@contextmanager
def get_session(database_url: str) -> Iterator[Session]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """One Engine (connection pool), reused across many Sessions — for a
    long-lived worker process handling many complaints, unlike get_session()
    which builds and disposes an Engine on every call (§Phase 4).

    expire_on_commit=False: the worker loop commits inside a `with
    session_factory() as session:` block and reads attributes off the
    returned ORM object (e.g. a claimed Job) after that block — and thus
    the session — has closed. The default (True) would try to refresh
    those attributes from a session that's gone, raising
    DetachedInstanceError instead of just returning last-known values."""
    engine = create_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)
