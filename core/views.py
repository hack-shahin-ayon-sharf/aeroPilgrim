from django.shortcuts import render
from .models import Search
from .forms import SearchForm
from .services.flight_api import get_flight_data


def searchView(request):

    form = SearchForm()

    return render(request, "core/home.html", {"form": form})


def searchResults(request):

    city_departure = request.GET.get("city_departure")
    city_arrival = request.GET.get("city_arrival")
    stay_days = request.GET.get("stay_days")
    timespan = request.GET.get("timespan_to_search")

    search = Search.objects.filter(
        city_departure=city_departure,
        city_arrival=city_arrival,
        stay_days=stay_days,
        timespan_to_search=timespan,
    ).first()

    if search and search.api_response:

        data = search.api_response

    else:

        data = get_flight_data(
            city_departure,
            city_arrival
        )

        search = Search.objects.create(
            city_departure=city_departure,
            city_arrival=city_arrival,
            stay_days=stay_days,
            timespan_to_search=timespan,
            api_response=data,
        )

    days = data["data"]["flights"]["days"]

    sorted_days = sorted(days, key=lambda x: x["price"])

    top_10 = sorted_days[:10]

    return render(request, "core/search_results.html", {
        "results": top_10,
        "city_departure": city_departure,
        "city_arrival": city_arrival,
    })