import socket
import urllib.error
import urllib.request

import pytest

from app.ical.fetcher import fetch_ical, IcalFetchError
from app.ical.parser import parse_ical


class DummyResponse:
    def __init__(self, data: bytes, status: int = 200, headers=None):
        self._data = data
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_ical_timeout(monkeypatch):
    def raise_timeout(*_args, **_kwargs):
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", raise_timeout)

    with pytest.raises(IcalFetchError):
        fetch_ical("http://example.com/ics", timeout=0.1)


def test_fetch_ical_http_500(monkeypatch):
    def bad_status(*_args, **_kwargs):
        return DummyResponse(b"broken", status=500)

    monkeypatch.setattr(urllib.request, "urlopen", bad_status)

    with pytest.raises(IcalFetchError):
        fetch_ical("http://example.com/ics")


def test_fetch_ical_empty_payload(monkeypatch):
    def ok_response(*_args, **_kwargs):
        return DummyResponse(b"", status=200)

    monkeypatch.setattr(urllib.request, "urlopen", ok_response)

    with pytest.raises(IcalFetchError):
        fetch_ical("http://example.com/ics")


def test_fetch_ical_broken_ics(monkeypatch):
    def ok_response(*_args, **_kwargs):
        return DummyResponse(b"not-ical", status=200)

    monkeypatch.setattr(urllib.request, "urlopen", ok_response)

    ics_text = fetch_ical("http://example.com/ics")
    parsed = parse_ical(ics_text, "UTC")

    assert parsed.items == []
    assert any("Failed to parse VCALENDAR" in warning for warning in parsed.warnings)
