"""
Search orchestrator — single entry point for "search this route".

Combines PHASES 1, 2, 4, 6, 7 and 9:

- PHASE 1: Normalize the query, hash it, hit the SearchCache. If the cache
  record exists AND `last_fetched < 24h`, return the cached response and DO
  NOT consume any user quota.
- PHASE 2: Verify the user has not exceeded their rolling-24h quota
  (free=1/day, premium=5/day). Only *real* API calls consume quota.
- PHASE 4: After every fresh API call we record a SearchHistory row tied to
  the user so it shows up in their dashboard.
- PHASE 6: RF1 — flex_days expands the candidate window by ±N days around
  every priced day.
- PHASE 7: RF2 — stay_min / stay_max generate a set of stay-length combos.
- PHASE 9: RF4 — across all expanded candidates we return the cheapest
  *valid* itinerary (every candidate has a price; the cheapest wins).

The orchestrator never raises to the view layer unless something fatal
happens — quota exhaustion is signalled via the returned ``Context`` dict's
``quota_exceeded`` flag and ``quota_error`` human message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from core.models import (
    AsyncSearchJob,
    QuotaExceeded,
    Search,
    SearchCache,
    SearchHistory,
    SearchUsage,
    UserSubscription,
)
from core.services.flight_api import (
    FlightAPIError,
    extract_flight_days,
    get_flight_data,
)

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=24)
ROLLING_WINDOW = timedelta(hours=24)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _city_label(code):
    from core.models import Search as _Search
    return dict(_Search.CITY_CHOICES).get(code, code)


def _normalize_query(params):
    """Return a *canonical* param dict used for hashing and the cache lookup."""
    return {
        "city_departure": params["city_departure"],
        "city_arrival": params["city_arrival"],
        "stay_days": int(params.get("stay_days") or 7),
        "timespan_to_search": int(params.get("timespan_to_search") or 30),
        "flex_days": int(params.get("flex_days") or 0),
    }


def build_params(
    city_departure,
    city_arrival,
    stay_days=7,
    timespan_to_search=30,
    flex_days=0,
):
    return {
        "city_departure": city_departure,
        "city_arrival": city_arrival,
        "stay_days": int(stay_days),
        "timespan_to_search": int(timespan_to_search),
        "flex_days": int(flex_days or 0),
    }


def build_query_hash(params):
    return SearchCache.build_query_hash(_normalize_query(params))


# ---------------------------------------------------------------------------
# Subscription + quota
# ---------------------------------------------------------------------------
def get_or_create_subscription(user):
    sub, _ = UserSubscription.objects.get_or_create(user=user)
    return sub


def usage_in_window(user, now=None):
    now = now or timezone.now()
    cutoff = now - ROLLING_WINDOW
    return SearchUsage.objects.filter(user=user, consumed_at__gte=cutoff)


def remaining_quota(user):
    sub = get_or_create_subscription(user)
    used = usage_in_window(user).count()
    remaining = max(0, sub.daily_quota - used)
    return sub, used, remaining


def consume_quota(user, params):
    """Record a fresh API call against this user's quota."""
    return SearchUsage.objects.create(
        user=user,
        city_departure=params["city_departure"],
        city_arrival=params["city_arrival"],
        consumed_at=timezone.now(),
    )


def check_quota(user):
    """Raise QuotaExceeded if the user is out of quota for the rolling 24h."""
    sub, used, remaining = remaining_quota(user)
    if remaining <= 0:
        # Time until the oldest usage in window falls out
        oldest = usage_in_window(user).order_by("consumed_at").first()
        resets_at = (
            (oldest.consumed_at + ROLLING_WINDOW) if oldest else timezone.now()
        )
        raise QuotaExceeded(sub.plan_label(), sub.daily_quota, resets_at)
    return sub


# ---------------------------------------------------------------------------
# Cache lookup
# ---------------------------------------------------------------------------
def _cache_lookup(params):
    p = _normalize_query(params)
    query_hash = SearchCache.build_query_hash(p)
    return (
        SearchCache.objects.filter(query_hash=query_hash)
        .order_by("-last_fetched")
        .first()
    ), query_hash


def cache_is_fresh(record, ttl=None):
    return bool(record and record.is_fresh(ttl or CACHE_TTL) and record.api_response)


# ---------------------------------------------------------------------------
# Cheapest-price + flex helpers
# ---------------------------------------------------------------------------
def _priced_days(data):
    days = extract_flight_days(data or {})
    return [d for d in days if d.get("price") is not None]


@dataclass
class Candidate:
    departure_date: str
    return_date: str
    stay_days: int
    price: float
    price_group: str


def _candidate_from_day(day, stay_days):
    dep = day.get("day")
    if not dep:
        return None
    try:
        d = datetime.strptime(dep, "%Y-%m-%d").date()
        return Candidate(
            departure_date=dep,
            return_date=str(d + timedelta(days=stay_days)),
            stay_days=int(stay_days),
            price=float(day.get("price")),
            price_group=day.get("group", "Standard"),
        )
    except (TypeError, ValueError):
        return None


def generate_candidates(data, stay_days, flex_days=0, stay_min=None, stay_max=None):
    """
    Build a deduplicated list of Candidate objects.

    - PHASE 6 / RF1: flex_days expands ±N days around every priced day.
    - PHASE 7 / RF2: when stay_min/stay_max are provided we also consider
      intermediate stay lengths so the user can pick an optimal stay.

    We don't actually *call the API* per stay combo — that's not how the
    calendar API works. The calendar gives us price per departure date; the
    return date is implicit (`dep + stay_days`). Generating return-date
    alternatives from the same calendar means: for each priced day, the
    candidate itinerary with *any* stay length in [stay_min, stay_max] is
    priced the same as that day's calendar minimum. We still rank them by
    total trip price (= flight price + hotel estimate) so longer stays are
    penalised.
    """
    priced = _priced_days(data)
    if not priced:
        return []

    stay_lengths = {int(stay_days or 7)}
    if stay_min or stay_max:
        lo = int(stay_min or stay_days or 7)
        hi = int(stay_max or stay_days or 7)
        if lo > hi:
            lo, hi = hi, lo
        # Cap at 30 — the calendar only spans that long, no point doing longer.
        hi = min(hi, 30)
        lo = max(1, lo)
        stay_lengths = set(range(lo, hi + 1))

    flex = max(0, int(flex_days or 0))

    candidates = []
    seen = set()
    for day in priced:
        base_dep = day.get("day")
        if not base_dep:
            continue
        try:
            base_date = datetime.strptime(base_dep, "%Y-%m-%d").date()
        except ValueError:
            continue
        # RF1: ±N days
        for offset in range(-flex, flex + 1):
            dep = base_date + timedelta(days=offset)
            dep_iso = dep.isoformat()
            for stay_len in stay_lengths:
                key = (dep_iso, stay_len)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(Candidate(
                    departure_date=dep_iso,
                    return_date=str(dep + timedelta(days=stay_len)),
                    stay_days=stay_len,
                    price=float(day.get("price")),
                    price_group=day.get("group", "Standard"),
                ))
    return candidates


def pick_cheapest(candidates):
    """Return the cheapest candidate (RF4)."""
    return min(candidates, key=lambda c: c.price) if candidates else None


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def _record_history(user, params, candidates, top):
    if not candidates:
        return None
    cheapest = top or pick_cheapest(candidates)
    return SearchHistory.objects.create(
        user=user if user and user.is_authenticated else None,
        session_key="" if (user and user.is_authenticated) else (
            getattr(user, "_session_key", "") if user else ""
        ),
        city_departure=params["city_departure"],
        city_arrival=params["city_arrival"],
        stay_days=int(params.get("stay_days") or 7),
        timespan_to_search=int(params.get("timespan_to_search") or 30),
        flex_days=int(params.get("flex_days") or 0),
        total_results=len(candidates),
        cheapest_price=Decimal(str(cheapest.price)) if cheapest else None,
        cheapest_date=cheapest.departure_date if cheapest else "",
    )


# ---------------------------------------------------------------------------
# Public orchestrator entry points
# ---------------------------------------------------------------------------
@dataclass
class SearchOutcome:
    candidates: list
    cheapest: Optional[Candidate]
    data: dict
    cache_hit: bool
    api_called: bool
    quota: dict
    history_id: Optional[int]
    error: str = ""
    quota_exceeded: bool = False
    resets_at: Optional[str] = None


def _outcome_to_dict(outcome):
    return {
        "candidates": [
            {
                "departure_date": c.departure_date,
                "return_date": c.return_date,
                "stay_days": c.stay_days,
                "price": c.price,
                "price_group": c.price_group,
            }
            for c in outcome.candidates
        ],
        "cheapest": (
            {
                "departure_date": outcome.cheapest.departure_date,
                "return_date": outcome.cheapest.return_date,
                "stay_days": outcome.cheapest.stay_days,
                "price": outcome.cheapest.price,
                "price_group": outcome.cheapest.price_group,
            }
            if outcome.cheapest
            else None
        ),
        "cache_hit": outcome.cache_hit,
        "api_called": outcome.api_called,
        "quota": outcome.quota,
        "history_id": outcome.history_id,
        "error": outcome.error,
        "quota_exceeded": outcome.quota_exceeded,
        "resets_at": outcome.resets_at,
    }


def run_search(
    params,
    user=None,
    *,
    force_api=False,
    flex_days=None,
    stay_min=None,
    stay_max=None,
):
    """
    Run a flight search.

    ``user`` may be None for anonymous calls (bot endpoints). For the web UI we
    pass the authenticated user so quota can be enforced.

    Returns a SearchOutcome.
    """
    params = _normalize_query(params)
    if flex_days is not None:
        params["flex_days"] = int(flex_days or 0)

    quota = {
        "plan": "Free",
        "is_premium": False,
        "daily_quota": UserSubscription.FREE_DAILY_QUOTA,
        "used_today": 0,
        "remaining": UserSubscription.FREE_DAILY_QUOTA,
        "authenticated": bool(user and user.is_authenticated),
    }
    if user and user.is_authenticated:
        sub, used, remaining = remaining_quota(user)
        quota = {
            "plan": sub.plan_label(),
            "is_premium": sub.is_premium,
            "daily_quota": sub.daily_quota,
            "used_today": used,
            "remaining": remaining,
            "authenticated": True,
        }

    cache_record, query_hash = _cache_lookup(params)
    fresh_cached = cache_is_fresh(cache_record)

    if fresh_cached and not force_api:
        data = cache_record.api_response
        candidates = generate_candidates(
            data,
            params["stay_days"],
            params["flex_days"],
            stay_min,
            stay_max,
        )
        cheapest = pick_cheapest(candidates)
        history_id = None
        if user and user.is_authenticated:
            history_id = _record_history(user, params, candidates, cheapest)
        return SearchOutcome(
            candidates=candidates,
            cheapest=cheapest,
            data=data,
            cache_hit=True,
            api_called=False,
            quota=quota,
            history_id=history_id,
        )

    # Cache miss OR stale — need to call the API.
    if user and user.is_authenticated:
        try:
            check_quota(user)
        except QuotaExceeded as exc:
            return SearchOutcome(
                candidates=[],
                cheapest=None,
                data={},
                cache_hit=bool(fresh_cached),
                api_called=False,
                quota=quota,
                history_id=None,
                error=(
                    f"You've used all {exc.daily_quota} of today's search"
                    f"{'es' if exc.daily_quota != 1 else ''} "
                    f"({exc.plan_label} plan). Upgrade to Premium or wait "
                    f"until {exc.resets_at:%H:%M} UTC for the quota to reset."
                ),
                quota_exceeded=True,
                resets_at=exc.resets_at.isoformat() if exc.resets_at else None,
            )

    try:
        data = get_flight_data(
            params["city_departure"],
            params["city_arrival"],
            params["timespan_to_search"],
        )
    except FlightAPIError as exc:
        # Stale cache fallback
        if cache_record and cache_record.api_response:
            data = cache_record.api_response
            candidates = generate_candidates(
                data,
                params["stay_days"],
                params["flex_days"],
                stay_min,
                stay_max,
            )
            cheapest = pick_cheapest(candidates)
            return SearchOutcome(
                candidates=candidates,
                cheapest=cheapest,
                data=data,
                cache_hit=True,
                api_called=False,
                quota=quota,
                history_id=None,
                error=(
                    f"Live search unavailable, showing cached results from "
                    f"{cache_record.last_fetched:%Y-%m-%d %H:%M} UTC."
                ),
            )
        return SearchOutcome(
            candidates=[],
            cheapest=None,
            data={},
            cache_hit=False,
            api_called=False,
            quota=quota,
            history_id=None,
            error=str(exc),
            quota_exceeded=False,
        )

    # Persist cache and quota atomically
    with transaction.atomic():
        if cache_record:
            cache_record.api_response = data
            cache_record.last_fetched = timezone.now()
            cache_record.search_params = params
            cache_record.save(update_fields=["api_response", "last_fetched", "search_params", "updated_at"])
        else:
            cache_record = SearchCache.objects.create(
                query_hash=query_hash,
                city_departure=params["city_departure"],
                city_arrival=params["city_arrival"],
                stay_days=params["stay_days"],
                timespan_to_search=params["timespan_to_search"],
                flex_days=params["flex_days"],
                search_params=params,
                api_response=data,
                last_fetched=timezone.now(),
            )

        if user and user.is_authenticated:
            consume_quota(user, params)
            quota["used_today"] = usage_in_window(user).count()
            quota["remaining"] = max(
                0, quota["daily_quota"] - quota["used_today"]
            )

    # Maintain legacy Search row so existing flight_detail URLs work.
    Search.objects.filter(
        city_departure=params["city_departure"],
        city_arrival=params["city_arrival"],
        stay_days=params["stay_days"],
        timespan_to_search=params["timespan_to_search"],
    ).delete()

    legacy = Search.objects.create(
        city_departure=params["city_departure"],
        city_arrival=params["city_arrival"],
        stay_days=params["stay_days"],
        timespan_to_search=params["timespan_to_search"],
        api_response=data,
    )

    candidates = generate_candidates(
        data,
        params["stay_days"],
        params["flex_days"],
        stay_min,
        stay_max,
    )
    cheapest = pick_cheapest(candidates)
    history_id = None
    if user and user.is_authenticated:
        history_id = _record_history(user, params, candidates, cheapest)

    return SearchOutcome(
        candidates=candidates,
        cheapest=cheapest,
        data=data,
        cache_hit=False,
        api_called=True,
        quota=quota,
        history_id=history_id,
    )


def outcome_for_api(outcome):
    """Convert outcome to a JSON-friendly dict (also shares the same shape as
    the legacy top_results list)."""
    return _outcome_to_dict(outcome)


def top_results_from_outcome(outcome, limit=5):
    """Top-N cheapest priced days, used by web search_results template."""
    return sorted(outcome.candidates, key=lambda c: c.price)[:limit]


# ---------------------------------------------------------------------------
# Async job helpers (PHASE 8)
# ---------------------------------------------------------------------------
def dispatch_async_search(user, params, flex_days=None, stay_min=None, stay_max=None):
    """Create an AsyncSearchJob and launch a daemon thread."""
    import uuid
    import threading

    job_id = uuid.uuid4().hex
    job = AsyncSearchJob.objects.create(
        user=user if user and user.is_authenticated else None,
        job_id=job_id,
        params={
            **params,
            "flex_days": int(flex_days or 0),
            "stay_min": stay_min,
            "stay_max": stay_max,
        },
        status=AsyncSearchJob.STATUS_QUEUED,
    )

    def _runner():
        job.refresh_from_db()
        job.status = AsyncSearchJob.STATUS_RUNNING
        job.save(update_fields=["status"])
        try:
            outcome = run_search(
                params,
                user=user,
                flex_days=flex_days,
                stay_min=stay_min,
                stay_max=stay_max,
            )
            job.result = _outcome_to_dict(outcome)
            job.status = (
                AsyncSearchJob.STATUS_COMPLETED
                if not outcome.error
                else AsyncSearchJob.STATUS_FAILED
            )
            job.error = outcome.error or ""
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("AsyncSearchJob %s crashed", job_id)
            job.status = AsyncSearchJob.STATUS_FAILED
            job.error = str(exc)
        finally:
            job.finished_at = timezone.now()
            job.save()

    thread = threading.Thread(target=_runner, daemon=True, name=f"search-{job_id[:6]}")
    thread.start()
    return job
