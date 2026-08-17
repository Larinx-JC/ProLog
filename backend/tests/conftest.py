"""Shared pytest fixtures for the backend test suite."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """A TestClient wrapping a freshly-built app instance, isolated per test."""
    return TestClient(create_app())
