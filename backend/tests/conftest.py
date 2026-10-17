import pytest

from app import llm


@pytest.fixture(autouse=True)
def reset_provider():
    yield
    llm.configure("claude")
