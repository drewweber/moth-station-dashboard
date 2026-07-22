"""Small iNaturalist API v1 client using only the Python standard library."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE = "https://api.inaturalist.org/v1"
PER_PAGE = 200


def _clean(params: dict[str, Any]) -> dict[str, str]:
    clean = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple, set)):
            clean[key] = ",".join(str(v) for v in value)
        else:
            clean[key] = str(value)
    return clean


def get_json(path: str, user_agent: str, **params: Any) -> dict[str, Any]:
    query = urlencode(_clean(params))
    url = f"{BASE}/{path}"
    if query:
        url = f"{url}?{query}"
    request = Request(url, headers={"User-Agent": user_agent})
    last_error: Exception | None = None

    for attempt in range(6):
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read().decode("utf-8")
            time.sleep(1.0)
            return json.loads(payload)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep(min(2**attempt, 30))

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to fetch {url}")


def first_observed_date(user_agent: str, **params: Any) -> str | None:
    """Return the earliest observed_on date for a query, or None."""
    data = get_json(
        "observations",
        user_agent=user_agent,
        per_page=1,
        order_by="observed_on",
        order="asc",
        **params,
    )
    results = data.get("results") or []
    return results[0].get("observed_on") if results else None


def latest_observation_id(user_agent: str, **params: Any) -> int:
    """Return the newest iNaturalist observation id for a query, or zero."""
    data = get_json(
        "observations",
        user_agent,
        per_page=1,
        order_by="id",
        order="desc",
        **params,
    )
    results = data.get("results") or []
    return int(results[0]["id"]) if results else 0


def iter_observations(
    params: dict[str, Any],
    user_agent: str,
    id_above: int = 0,
    max_pages: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield matching observations using an id cursor.

    The id cursor avoids iNaturalist's normal deep-pagination ceiling and makes
    repeated station syncs cheap.
    """
    page_count = 0
    cursor = id_above
    while True:
        data = get_json(
            "observations",
            user_agent=user_agent,
            per_page=PER_PAGE,
            order_by="id",
            order="asc",
            id_above=cursor,
            **params,
        )
        results = data.get("results") or []
        if not results:
            return
        for obs in results:
            yield obs
        cursor = int(results[-1]["id"])
        page_count += 1
        if len(results) < PER_PAGE:
            return
        if max_pages is not None and page_count >= max_pages:
            return


def iter_species_counts(
    params: dict[str, Any],
    user_agent: str,
) -> Iterator[dict[str, Any]]:
    """Yield every taxon count returned by a bounded iNaturalist search."""
    page = 1
    while True:
        data = get_json(
            "observations/species_counts",
            user_agent=user_agent,
            per_page=PER_PAGE,
            page=page,
            **params,
        )
        results = data.get("results") or []
        for item in results:
            yield item
        total = int(data.get("total_results") or 0)
        if not results or page * PER_PAGE >= total:
            return
        page += 1
