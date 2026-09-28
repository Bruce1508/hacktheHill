from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@contextmanager
def get_session(database_url: str) -> Iterator[Session]:
    engine = create_engine(database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()
