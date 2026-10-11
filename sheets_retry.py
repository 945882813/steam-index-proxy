"""Retry only transient Google Sheets API failures.

Google's Sheets per-user read/write quotas refresh each minute. A shared
service account can hit 429 if several workflows write at once.
"""
import random
import time
import gspread
from gspread.exceptions import APIError


class RetrySheetsHTTPClient(gspread.HTTPClient):
    """Thin gspread HTTP client: bounded exponential backoff on 429/5xx."""

    def request(self, *args, **kwargs):
        for attempt in range(5):
            try:
                return super().request(*args, **kwargs)
            except APIError as exc:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                if code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise
                time.sleep(min(60, 6 * (2 ** attempt)) + random.uniform(0.0, 1.0))
        raise RuntimeError("unreachable")


def authorize(credentials):
    return gspread.authorize(credentials, http_client=RetrySheetsHTTPClient)
