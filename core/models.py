import hashlib
import json

from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q, F
from datetime import timedelta
from django.utils import timezone

class Search(models.Model):

    CITY_CHOICES = (
        ("JED", "Jeddah"),
        ("MED", "Medina"),
        ("DAC", "Dhaka"),
        ("CGP", "Chattogram"),
        ("ZYL", "Sylhet"),
    )

    DAYS_CHOICES = (
        (7, "7 Days"),
        (10, "10 Days"),
        (15, "15 Days"),
        (20, "20 Days"),
        (30, "30 Days"),
    )

    TIMESPAN_CHOICES = (
        (7, "7 Days"),
        (30, "30 Days"),
        (90, "3 Months"),
        (180, "6 Months"),
        (365, "1 Year"),
    )

    city_departure = models.CharField(
        max_length=3,
        choices=CITY_CHOICES,
        default="DAC"
    )

    city_arrival = models.CharField(
        max_length=3,
        choices=CITY_CHOICES,
        default="JED"
    )

    stay_days = models.IntegerField(
        choices=DAYS_CHOICES,
        default=7
    )

    timespan_to_search = models.IntegerField(
        choices=TIMESPAN_CHOICES,
        default=30
    )

    api_response = models.JSONField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.city_departure} to {self.city_arrival} in {self.timespan_to_search} days"


class SearchRateLimit(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    last_api_call_at = models.DateTimeField()

    def __str__(self):
        return f"{self.ip_address} @ {self.last_api_call_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# PHASE 1 — Dedicated SearchCache model.
#
# `Search` continues to act as the *legacy, per-call persisted search* (and is
# referenced by URL `/search/flight/<id>/<date>/`). `SearchCache` is the
# normalized, hash-addressed API-response cache used by the orchestrator so the
# frontend never has to know whether the data came from the cache or a fresh
# external call.
# ---------------------------------------------------------------------------
class SearchCache(models.Model):
    query_hash = models.CharField(max_length=64, unique=True, db_index=True)
    city_departure = models.CharField(max_length=3)
    city_arrival = models.CharField(max_length=3)
    stay_days = models.IntegerField(default=7)
    timespan_to_search = models.IntegerField(default=30)
    flex_days = models.IntegerField(default=0)
    search_params = models.JSONField(default=dict)
    api_response = models.JSONField(null=True, blank=True)
    last_fetched = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city_departure", "city_arrival"]),
            models.Index(fields=["last_fetched"]),
        ]

    def __str__(self):
        return (
            f"Cache {self.city_departure}->{self.city_arrival} "
            f"stay={self.stay_days} span={self.timespan_to_search} "
            f"@ {self.last_fetched:%Y-%m-%d %H:%M}"
        )

    @staticmethod
    def build_query_hash(params):
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_fresh(self, ttl=None):
        ttl = ttl or timedelta(hours=24)
        return (timezone.now() - self.last_fetched) < ttl

    @property
    def age_hours(self):
        delta = timezone.now() - self.last_fetched
        return delta.total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# PHASE 2 — Per-user subscription + quota tracking.
# ---------------------------------------------------------------------------
class UserSubscription(models.Model):
    PLAN_FREE = "free"
    PLAN_PREMIUM = "premium"
    PLAN_CHOICES = (
        (PLAN_FREE, "Free"),
        (PLAN_PREMIUM, "Premium"),
    )

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_FREE)
    is_premium = models.BooleanField(default=False)
    upgraded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_payment_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    FREE_DAILY_QUOTA = 1
    PREMIUM_DAILY_QUOTA = 5

    def __str__(self):
        return f"{self.user.username}: {self.plan}"

    @property
    def daily_quota(self):
        return self.PREMIUM_DAILY_QUOTA if self.is_premium else self.FREE_DAILY_QUOTA

    def plan_label(self):
        return "Premium" if self.is_premium else "Free"


class SearchUsage(models.Model):
    """Records each *real* API call so we can enforce a rolling-24h quota."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="search_usage"
    )
    consumed_at = models.DateTimeField(default=timezone.now, db_index=True)
    city_departure = models.CharField(max_length=3)
    city_arrival = models.CharField(max_length=3)

    class Meta:
        indexes = [
            models.Index(fields=["user", "consumed_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.consumed_at:%Y-%m-%d %H:%M}"


class QuotaExceeded(Exception):
    """Raised when the user has exhausted their rolling-24h API search quota."""

    def __init__(self, plan_label, daily_quota, resets_at):
        super().__init__(
            f"Quota exceeded for '{plan_label}' plan "
            f"({daily_quota}/day). Resets at {resets_at:%H:%M} UTC."
        )
        self.plan_label = plan_label
        self.daily_quota = daily_quota
        self.resets_at = resets_at


# ---------------------------------------------------------------------------
# PHASE 5 — Watchlists.
# ---------------------------------------------------------------------------
class Watchlist(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="watchlists"
    )
    name = models.CharField(max_length=120, default="My Watchlist")
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    budget_usd = models.PositiveIntegerField(null=True, blank=True)
    stay_min_days = models.PositiveIntegerField(default=7)
    stay_max_days = models.PositiveIntegerField(default=15)
    target_departure = models.DateField(null=True, blank=True)
    notify_ready = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.origin}->{self.destination}"


# ---------------------------------------------------------------------------
# PHASE 3 — Demo SSLCommerz payment records.
# ---------------------------------------------------------------------------
class PaymentTransaction(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="payments"
    )
    tran_id = models.CharField(max_length=64, unique=True)
    amount_usd = models.DecimalField(max_digits=8, decimal_places=2, default=5.00)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    gateway_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tran_id} ({self.status})"


# ---------------------------------------------------------------------------
# PHASE 8 — Async search job tracking.
# ---------------------------------------------------------------------------
class AsyncSearchJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="async_jobs",
        null=True,
        blank=True,
    )
    job_id = models.CharField(max_length=64, unique=True, db_index=True)
    params = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED
    )
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# PHASE 4 — Search history (per-user persistence so users can re-run previous
# API calls). Distinct from SearchCache so caches stay normalized, but every
# successful *fresh* API call records here as well.
# ---------------------------------------------------------------------------
class SearchHistory(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="search_history",
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=64, blank=True, default="")
    city_departure = models.CharField(max_length=3)
    city_arrival = models.CharField(max_length=3)
    stay_days = models.IntegerField(default=7)
    timespan_to_search = models.IntegerField(default=30)
    flex_days = models.IntegerField(default=0)
    total_results = models.IntegerField(default=0)
    cheapest_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    cheapest_date = models.CharField(max_length=10, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["city_departure", "city_arrival"]),
        ]

    def __str__(self):
        anon = self.user.username if self.user else f"anon:{self.session_key[:8]}"
        return f"{anon} {self.city_departure}->{self.city_arrival}"
