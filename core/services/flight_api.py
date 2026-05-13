import requests
from django.conf import settings
from datetime import date


def get_flight_data(city_departure, city_arrival):

    url = "https://sky-scrapper.p.rapidapi.com/api/v1/flights/getPriceCalendar"

    querystring = {
        "originSkyId": city_departure,
        "destinationSkyId": city_arrival,
        "fromDate": str(date.today()),
        "currency": "USD",
    }

    headers = {
        "x-rapidapi-key": settings.API_KEY,
        "x-rapidapi-host": settings.API_HOST,
    }

    response = requests.get(
        url,
        headers=headers,
        params=querystring,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()