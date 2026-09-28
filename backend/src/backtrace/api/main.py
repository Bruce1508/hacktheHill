import os
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import select

from backtrace.api.auth import CurrentUser, current_user
from backtrace.contracts.complaints import ComplaintOut
from backtrace.db.models import Complaint
from backtrace.db.session import get_session

app = FastAPI(title="Backtrace API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/complaints")
def list_complaints(
    _user: Annotated[CurrentUser, Depends(current_user)],
    limit: int = 100,
    offset: int = 0,
) -> list[ComplaintOut]:
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        rows = session.execute(
            select(Complaint).order_by(Complaint.received_at).limit(limit).offset(offset)
        ).scalars().all()
        return [ComplaintOut.model_validate(row) for row in rows]
