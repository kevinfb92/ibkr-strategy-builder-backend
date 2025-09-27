"""
Pytest fixtures for tests in this repo.

Provides a `fake_ibkr` fixture and automatically monkeypatches
`app.services.ibkr_service.IBKRService` to return the fake instance.
"""
import pytest
from tests.helpers.fake_ibkr import FakeIBKR


@pytest.fixture
def fake_ibkr(monkeypatch):
    fake = FakeIBKR()

    class Factory:
        def __call__(self, *args, **kwargs):
            return fake

    # Monkeypatch the IBKRService factory used in code under test
    try:
        import app.services.ibkr_service as ibkr_mod
        monkeypatch.setattr(ibkr_mod, 'IBKRService', Factory())
    except Exception:
        # If module not importable at fixture creation time, tests can still import and monkeypatch later
        pass

    return fake
