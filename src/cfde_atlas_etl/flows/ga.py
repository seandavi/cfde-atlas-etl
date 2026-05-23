"""Prefect flow: Google Analytics reports per property.

Properties are loaded from raw/manual-ga-properties.yaml (we cannot direct DCC
teams, so the access-granted set is curated). For each property we run a fixed
catalog of GA4 Data API runReport calls and land each response into
raw.ga_reports.

A property without service-account access yields 403 from the Data API; the
flow logs that and continues, so one missing DCC does not block the others.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.models.ga import GaProperty, GaReport
from cfde_atlas_etl.sinks.postgres import upsert_raw_ga_properties, upsert_raw_ga_reports
from cfde_atlas_etl.sources.google_analytics import _access_token, report_request, run_report

PROPERTIES_PATH = Path("raw/manual-ga-properties.yaml")
DEFAULT_LOOKBACK_DAYS = 365

REPORT_CATALOG: dict[str, dict[str, Any]] = {
    "over_time": {
        "dimensions": ["date"],
        "metrics": [
            "screenPageViews",
            "totalUsers",
            "sessions",
            "averageSessionDuration",
            "engagementRate",
            "newUsers",
        ],
    },
    "top_pages": {
        "dimensions": ["pagePath", "pageTitle"],
        "metrics": ["screenPageViews", "totalUsers", "averageSessionDuration"],
        "limit": 500,
        "order_by_metric": "screenPageViews",
    },
    "top_countries": {
        "dimensions": ["country"],
        "metrics": ["totalUsers", "screenPageViews"],
        "limit": 250,
    },
    "top_regions": {"dimensions": ["region"], "metrics": ["totalUsers"], "limit": 250},
    "top_cities": {"dimensions": ["city"], "metrics": ["totalUsers"], "limit": 250},
    "top_continents": {"dimensions": ["continent"], "metrics": ["totalUsers"]},
    "top_languages": {"dimensions": ["language"], "metrics": ["totalUsers"], "limit": 100},
    "top_devices": {"dimensions": ["deviceCategory"], "metrics": ["totalUsers"]},
    "top_oses": {"dimensions": ["operatingSystem"], "metrics": ["totalUsers"]},
    "traffic_sources": {
        "dimensions": ["sessionDefaultChannelGroup", "sessionSource", "sessionMedium"],
        "metrics": ["sessions", "totalUsers"],
        "limit": 500,
    },
    "top_referrers": {"dimensions": ["pageReferrer"], "metrics": ["sessions"], "limit": 250},
    "top_search_terms": {"dimensions": ["searchTerm"], "metrics": ["eventCount"], "limit": 250},
    "events_by_name": {
        "dimensions": ["eventName"],
        "metrics": ["eventCount", "totalUsers"],
        "limit": 250,
    },
}


@task
def load_properties_yaml(path: Path = PROPERTIES_PATH) -> list[GaProperty]:
    if not path.exists():
        return []
    payload: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    raw = payload.get("properties") or []
    return [GaProperty.model_validate(r) for r in raw]


@task
async def write_properties(records: list[GaProperty]) -> int:
    return await upsert_raw_ga_properties(records)


@task(retries=2, retry_delay_seconds=15)
async def fetch_property_reports(
    prop: GaProperty,
    *,
    token: str,
    client: httpx.AsyncClient,
    period_start: date,
    period_end: date,
) -> list[GaReport]:
    logger = get_run_logger()
    out: list[GaReport] = []
    for kind, spec in REPORT_CATALOG.items():
        body = report_request(
            dimensions=spec["dimensions"],
            metrics=spec["metrics"],
            date_range=(period_start.isoformat(), period_end.isoformat()),
            limit=spec.get("limit"),
            order_by_metric=spec.get("order_by_metric"),
        )
        try:
            response = await run_report(prop.property_id, body, token=token, client=client)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "GA report %s on property %s failed: %s — skipping",
                kind,
                prop.property_id,
                exc.response.status_code,
            )
            continue
        out.append(
            GaReport(
                property_id=prop.property_id,
                report_kind=kind,
                period_start=period_start,
                period_end=period_end,
                response=response,
            )
        )
    return out


@task
async def write_reports(records: list[GaReport]) -> int:
    return await upsert_raw_ga_reports(records)


@flow(name="load-ga")
async def load_ga(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> int:
    logger = get_run_logger()

    properties = load_properties_yaml()
    if not properties:
        logger.warning("No GA properties configured in %s — skipping flow", PROPERTIES_PATH)
        return 0

    await write_properties(properties)
    logger.info("Wrote %d GA properties to raw.ga_properties", len(properties))

    token = _access_token()
    period_end = date.today()
    period_start = period_end - timedelta(days=lookback_days)

    async with httpx.AsyncClient(timeout=60.0) as client:
        per_property: list[list[GaReport]] = await asyncio.gather(
            *(
                fetch_property_reports(
                    p, token=token, client=client, period_start=period_start, period_end=period_end
                )
                for p in properties
            )
        )

    flattened: list[GaReport] = [r for batch in per_property for r in batch]
    written = await write_reports(flattened)
    logger.info("Upserted %d GA report rows", written)
    return written


if __name__ == "__main__":
    asyncio.run(load_ga())
