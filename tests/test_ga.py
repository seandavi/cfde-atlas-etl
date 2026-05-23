"""Tests for the GA source. All network mocked; auth bypassed."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sources.google_analytics import (
    DATA_API_BASE,
    report_request,
    run_report,
)


def test_report_request_serializes_dimensions_metrics_dates() -> None:
    body = report_request(
        dimensions=["date"],
        metrics=["screenPageViews", "totalUsers"],
        date_range=("2026-01-01", "2026-05-22"),
        limit=100,
        order_by_metric="screenPageViews",
    )
    assert body["dimensions"] == [{"name": "date"}]
    assert body["metrics"] == [{"name": "screenPageViews"}, {"name": "totalUsers"}]
    assert body["dateRanges"] == [{"startDate": "2026-01-01", "endDate": "2026-05-22"}]
    assert body["limit"] == 100
    assert body["orderBys"][0]["metric"]["metricName"] == "screenPageViews"


@pytest.mark.asyncio
async def test_run_report_posts_with_bearer_token(httpx_mock: HTTPXMock) -> None:
    property_id = "123456789"
    url = f"{DATA_API_BASE}/properties/{property_id}:runReport"
    httpx_mock.add_response(
        method="POST",
        url=url,
        json={
            "rows": [
                {
                    "dimensionValues": [{"value": "20260501"}],
                    "metricValues": [
                        {"value": "42"},
                        {"value": "10"},
                        {"value": "5"},
                        {"value": "12.5"},
                    ],
                }
            ]
        },
    )

    body = report_request(
        dimensions=["date"],
        metrics=["screenPageViews", "totalUsers", "sessions", "averageSessionDuration"],
        date_range=("2026-04-01", "2026-05-22"),
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await run_report(property_id, body, token="fake-token", client=client)

    assert result["rows"][0]["metricValues"][0]["value"] == "42"
    sent = httpx_mock.get_requests()[0]
    assert sent.headers["Authorization"] == "Bearer fake-token"
