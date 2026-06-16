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
