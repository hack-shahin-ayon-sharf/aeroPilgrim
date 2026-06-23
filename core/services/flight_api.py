import requests
from datetime import date, timedelta

from django.conf import settings

from core.models import Search

BASE_URL = "https://sky-scrapper.p.rapidapi.com/api/v1/flights"

CITY_SEARCH_QUERIES = dict(Search.CITY_CHOICES)

_airport_cache = {}


class FlightAPIError(Exception):
    """Raised when the flight API returns an error or invalid payload."""


def _api_headers():
    if not settings.API_KEY:
        raise FlightAPIError("Flight search is not configured. Please try again later.")
    return {
        "x-rapidapi-key": settings.API_KEY,
        "x-rapidapi-host": settings.API_HOST,
    }


def _api_get(path, params):
    try:
        response = requests.get(
            f"{BASE_URL}/{path}",
            headers=_api_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FlightAPIError(
            "Unable to reach the flight search service. Please try again later."
        ) from exc
    return response.json()


def resolve_airport(city_code):
    if city_code in _airport_cache:
        return _airport_cache[city_code]

    query = CITY_SEARCH_QUERIES.get(city_code, city_code)
    payload = _api_get("searchAirport", {"query": query})

    airports = payload.get("data")
    if not airports:
        raise FlightAPIError(
            f"Could not find airport information for {query}. Please try another city."
        )

    airport = airports[0]
    flight_params = airport.get("navigation", {}).get("relevantFlightParams", {})
    sky_id = flight_params.get("skyId")
    entity_id = flight_params.get("entityId")
    if not sky_id or not entity_id:
        raise FlightAPIError(
            f"Airport lookup for {query} returned incomplete data. Please try again."
        )

    resolved = {"skyId": sky_id, "entityId": entity_id}
    _airport_cache[city_code] = resolved
    return resolved


def extract_flight_days(data):
    days = data.get("data", {}).get("flights", {}).get("days", [])
    if not isinstance(days, list):
        return []
    return days


def get_flight_data(city_departure, city_arrival, timespan_to_search=30):
    origin = resolve_airport(city_departure)
    destination = resolve_airport(city_arrival)

    from_date = date.today()
    to_date = from_date + timedelta(days=timespan_to_search)

    payload = _api_get(
        "getPriceCalendar",
        {
            "originSkyId": origin["skyId"],
            "destinationSkyId": destination["skyId"],
            "originEntityId": origin["entityId"],
            "destinationEntityId": destination["entityId"],
            "fromDate": str(from_date),
            "toDate": str(to_date),
            "currency": "USD",
        },
    )

    days = extract_flight_days(payload)
    if not days:
        raise FlightAPIError(
            "No flights were found for this route and date range. "
            "Try different cities or a wider search window."
        )

    return payload
