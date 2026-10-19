import pytest
from fastapi.testclient import TestClient
from stt_lab.api import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c
