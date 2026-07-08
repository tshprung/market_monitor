import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import data_fetch


def test_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)  # don't actually wait in tests

    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("transient SSL hiccup")
        return "success"

    result = data_fetch._fetch_with_retry(flaky)
    assert result == "success"
    assert calls["count"] == 3


def test_retry_raises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    def always_fails():
        raise ConnectionError("persistent failure")

    with pytest.raises(ConnectionError, match="persistent failure"):
        data_fetch._fetch_with_retry(always_fails)


def test_retry_does_not_retry_on_first_success(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: (_ for _ in ()).throw(
        AssertionError("should not sleep if first attempt succeeds")
    ))

    calls = {"count": 0}

    def works_first_time():
        calls["count"] += 1
        return "ok"

    result = data_fetch._fetch_with_retry(works_first_time)
    assert result == "ok"
    assert calls["count"] == 1
