from datetime import timedelta

from django.utils import timezone

from core.models import Search, SearchRateLimit

SEARCH_COOLDOWN = timedelta(days=7)


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def find_cached_search(city_departure, city_arrival, stay_days, timespan):
    return (
        Search.objects.filter(
            city_departure=city_departure,
            city_arrival=city_arrival,
            stay_days=stay_days,
            timespan_to_search=timespan,
            api_response__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )


def ip_can_call_api(request):
    ip = get_client_ip(request)
    if not ip:
        return False

    cutoff = timezone.now() - SEARCH_COOLDOWN
    return not SearchRateLimit.objects.filter(
        ip_address=ip,
        last_api_call_at__gte=cutoff,
    ).exists()


def record_api_call(request):
    ip = get_client_ip(request)
    if not ip:
        return

    SearchRateLimit.objects.update_or_create(
        ip_address=ip,
        defaults={"last_api_call_at": timezone.now()},
    )
