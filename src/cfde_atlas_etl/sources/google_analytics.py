"""Google Analytics Data API v1beta client.

Hits the REST endpoint directly with httpx + a service-account access token —
intentionally lighter than the gRPC SDK so we can mock it cleanly in tests.

Auth: GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account JSON file.
The service account must have Viewer access on each GA4 property
(documented in README — each DCC adds the SA email manually).
"""

from __future__ import annotations

from typing import Any

import httpx

DATA_API_BASE = "https://analyticsdata.googleapis.com/v1beta"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _load_credentials() -> Any:
    """Lazy-import google-auth so callers without GA can skip the dep at runtime."""
    from google.auth import default

    creds, _ = default(scopes=SCOPES)
    return creds


def _access_token(credentials: Any | None = None) -> str:
    from google.auth.transport.requests import Request

    creds = credentials if credentials is not None else _load_credentials()
    if not getattr(creds, "valid", False):
        creds.refresh(Request())
    return str(creds.token)


def report_request(
    *,
    dimensions: list[str],
    metrics: list[str],
    date_range: tuple[str, str],
    limit: int | None = None,
    order_by_metric: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "dateRanges": [{"startDate": date_range[0], "endDate": date_range[1]}],
    }
    if limit:
        body["limit"] = limit
    if order_by_metric:
        body["orderBys"] = [
            {"metric": {"metricName": order_by_metric}, "desc": True},
        ]
    return body


async def run_report(
    property_id: str,
    request_body: dict[str, Any],
    *,
    token: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Call properties/{property}:runReport once and return decoded JSON."""
    url = f"{DATA_API_BASE}/properties/{property_id}:runReport"
    response = await client.post(
        url,
        json=request_body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()
