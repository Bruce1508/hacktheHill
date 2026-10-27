import os

import pytest
from fastapi.testclient import TestClient

from backtrace.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def database_url_pipeline() -> str:
    return os.environ["DATABASE_URL_PIPELINE"]
