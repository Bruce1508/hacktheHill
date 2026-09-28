import os
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyCookie, APIKeyHeader


Role = Literal["agent", "team_lead", "compliance"]


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: str
    role: Role


DEMO_USERS: dict[str, CurrentUser] = {
    "demo-agent": CurrentUser(user_id="demo-agent", role="agent"),
    "demo-team-lead": CurrentUser(
        user_id="demo-team-lead",
        role="team_lead",
    ),
    "demo-compliance": CurrentUser(
        user_id="demo-compliance",
        role="compliance",
    ),
}

demo_user_header = APIKeyHeader(
    name="X-Demo-User",
    scheme_name="DemoUserHeader",
    auto_error=False,
)
demo_user_cookie = APIKeyCookie(
    name="demo_user",
    scheme_name="DemoUserCookie",
    auto_error=False,
)


def current_user(
    header_user: Annotated[str | None, Security(demo_user_header)],
    cookie_user: Annotated[str | None, Security(demo_user_cookie)],
) -> CurrentUser:
    if os.environ.get("AUTH_MODE") != "dev":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    user_id = header_user if header_user is not None else cookie_user
    user = DEMO_USERS.get(user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid demo user",
        )
    return user
