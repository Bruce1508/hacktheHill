from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@contextmanager
def get_session(database_url: str) -> Iterator[Session]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
