from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta

from .models import Search
from .forms import SearchForm
from .services.flight_api import get_flight_data


def searchView(request):

    form = SearchForm()

    return render(request, "core/home.html", {"form": form})


def searchResults(request):

    city_departure = request.GET.get("city_departure")
    city_arrival = request.GET.get("city_arrival")

    stay_days = int(request.GET.get("stay_days"))
    timespan = int(request.GET.get("timespan_to_search"))

    # Get latest matching search
    search = Search.objects.filter(
        city_departure=city_departure,
        city_arrival=city_arrival,
        stay_days=stay_days,
        timespan_to_search=timespan,
    ).order_by("-created_at").first()

    # Cache expiry rule (1 day)
    one_day_ago = timezone.now() - timedelta(days=1)

    cache_valid = (
        search
        and search.api_response
        and search.created_at >= one_day_ago
    )

    if cache_valid:

        print("FROM CACHE")

        data = search.api_response

    else:

        print("FROM API")

        data = get_flight_data(
            city_departure,
            city_arrival
        )

        # Optional cleanup: remove old duplicates
        Search.objects.filter(
            city_departure=city_departure,
            city_arrival=city_arrival,
            stay_days=stay_days,
            timespan_to_search=timespan,
        ).delete()

        search = Search.objects.create(
            city_departure=city_departure,
            city_arrival=city_arrival,
            stay_days=stay_days,
            timespan_to_search=timespan,
            api_response=data,
        )

    # Extract + clean results
    days = data["data"]["flights"]["days"]

    top_10 = sorted(days, key=lambda x: x["price"])[:10]

    return render(request, "core/search_results.html", {
        "results": top_10,
        "city_departure": city_departure,
        "city_arrival": city_arrival,
    })