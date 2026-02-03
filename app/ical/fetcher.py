import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class IcalFetchError(RuntimeError):
    pass


def _decode_ics(data: bytes, content_type: Optional[str]) -> str:
    charset = None
    if content_type:
        try:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        except Exception:
            charset = None

    candidates = []
    if charset:
        candidates.append(charset)
    candidates.extend(["utf-8", "utf-8-sig", "cp1251", "latin-1"])

    for enc in candidates:
        try:
            return data.decode(enc)
        except Exception:
            continue

    return data.decode("utf-8", errors="replace")


def fetch_ical(url: str, timeout: float = 10.0) -> str:
    if not url or not isinstance(url, str):
        raise IcalFetchError("URL is required for iCal fetch.")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BotRasp/1.0",
            "Accept": "text/calendar, text/plain, */*",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status and status != 200:
                logger.error("iCal fetch failed with status=%s for url=%s", status, url)
                raise IcalFetchError(f"Unexpected HTTP status: {status}")
            data = response.read()
            if not data:
                logger.error("iCal fetch returned empty body for url=%s", url)
                raise IcalFetchError("Empty iCal response")
            content_type = response.headers.get("Content-Type")
            return _decode_ics(data, content_type)
    except urllib.error.HTTPError as exc:
        logger.error("iCal HTTP error for url=%s status=%s reason=%s", url, exc.code, exc.reason)
        raise IcalFetchError(f"HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        logger.error("iCal URL error for url=%s reason=%s", url, exc.reason)
        raise IcalFetchError("Network error while fetching iCal.") from exc
    except Exception as exc:
        logger.exception("Unexpected iCal fetch error for url=%s", url)
        raise IcalFetchError("Unexpected error while fetching iCal.") from exc
