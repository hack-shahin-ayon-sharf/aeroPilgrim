from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import timedelta, datetime

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
import json

from .models import Search
from .forms import SearchForm, RegistrationForm, LoginForm
from .services.flight_api import FlightAPIError, extract_flight_days, get_flight_data
from .services.ai_service import AI_ACTIONS, generate_ai_response
from .services.chat_service import build_trip_chat_context
from .services.n8n_chat_service import N8nChatError, send_n8n_message
from .services.rate_limit import (
    find_cached_search,
    ip_can_call_api,
    record_api_call,
)


def _city_label(code):
    return dict(Search.CITY_CHOICES).get(code, code)


def _normalize_flight(day_obj):
    return {
        "flight_date": day_obj.get("day"),
        "price": day_obj.get("price"),
        "price_group": day_obj.get("group", "Standard"),
    }


def _get_flight_from_search(search, flight_date):
    days = extract_flight_days(search.api_response or {})
    for day in days:
        if day.get("day") == flight_date:
            return _normalize_flight(day)
    return None


def _build_trip_context(search, flight):
    return_date = None
    if flight["flight_date"]:
        depart = datetime.strptime(flight["flight_date"], "%Y-%m-%d").date()
        return_date = depart + timedelta(days=search.stay_days)

    return {
        "city_departure": search.city_departure,
        "city_arrival": search.city_arrival,
        "city_departure_label": _city_label(search.city_departure),
        "city_arrival_label": _city_label(search.city_arrival),
        "stay_days": search.stay_days,
        "timespan_to_search": search.timespan_to_search,
        "flight_date": flight["flight_date"],
        "price": flight["price"],
        "price_group": flight["price_group"],
        "return_date": str(return_date) if return_date else None,
    }


def registerView(request):
    """Handle user registration"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! You are now logged in.')
            return redirect('home')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RegistrationForm()
    
    return render(request, 'core/register.html', {'form': form})


def loginView(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('home')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'core/login.html', {'form': form})


def logoutView(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


def searchView(request):
    """Display search form on home page"""
    form = SearchForm()
    return render(request, "core/home.html", {"form": form})


@login_required(login_url='login')
def searchResults(request):
    """Display search results - only accessible to logged-in users"""

    city_departure = request.GET.get("city_departure")
    city_arrival = request.GET.get("city_arrival")

    if not city_departure or not city_arrival:
        messages.error(request, "Please complete your search first.")
        return redirect("home")

    try:
        stay_days = int(request.GET.get("stay_days", 7))
        timespan = int(request.GET.get("timespan_to_search", 30))
    except (TypeError, ValueError):
        messages.error(request, "Invalid search parameters.")
        return redirect("home")

    results_context = {
        "city_departure": _city_label(city_departure),
        "city_arrival": _city_label(city_arrival),
        "stay_days": stay_days,
    }

    search = find_cached_search(
        city_departure, city_arrival, stay_days, timespan
    )
    data = None
    had_stale_cache = False

    if search and extract_flight_days(search.api_response or {}):
        data = search.api_response
    elif search:
        had_stale_cache = True
        search.delete()
        search = None

    if data is None:
        if not ip_can_call_api(request):
            return render(request, "core/search_results.html", {
                **results_context,
                "results": [],
                "search": None,
                "rate_limit_exceeded": not had_stale_cache,
            })

        try:
            data = get_flight_data(city_departure, city_arrival, timespan)
        except FlightAPIError as exc:
            messages.error(request, str(exc))
            return render(request, "core/search_results.html", {
                **results_context,
                "results": [],
                "search": None,
            })

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
        record_api_call(request)

    days = extract_flight_days(data)
    priced_days = [d for d in days if d.get("price") is not None]
    top_results = [
        _normalize_flight(d)
        for d in sorted(priced_days, key=lambda x: x["price"])[:5]
    ]

    return render(request, "core/search_results.html", {
        **results_context,
        "results": top_results,
        "search": search,
    })




@login_required(login_url='login')
def flightDetail(request, search_id, flight_date):
    """Show full details for a selected flight date"""
    search = get_object_or_404(Search, pk=search_id)
    flight = _get_flight_from_search(search, flight_date)

    if not flight:
        messages.error(request, "This flight option is no longer available.")
        return redirect(
            f"/search/?city_departure={search.city_departure}"
            f"&city_arrival={search.city_arrival}"
            f"&stay_days={search.stay_days}"
            f"&timespan_to_search={search.timespan_to_search}"
        )

    trip = _build_trip_context(search, flight)

    return render(request, "core/flight_detail.html", {
        "search": search,
        "flight": flight,
        "trip": trip,
        "ai_actions": AI_ACTIONS,
        "city_departure": trip["city_departure_label"],
        "city_arrival": trip["city_arrival_label"],
    })






@login_required(login_url='login')
@require_POST
def aiAction(request, search_id, flight_date):
    """Generate AI response for a trip action button"""
    search = get_object_or_404(Search, pk=search_id)
    flight = _get_flight_from_search(search, flight_date)

    if not flight:
        return JsonResponse({"success": False, "error": "Flight not found."}, status=404)

    try:
        body = json.loads(request.body)
        action = body.get("action")
    except json.JSONDecodeError:
        action = request.POST.get("action")

    if action not in AI_ACTIONS:
        return JsonResponse({"success": False, "error": "Invalid action."}, status=400)

    context = _build_trip_context(search, flight)
    content = generate_ai_response(action, context)

    return JsonResponse({
        "success": True,
        "action": action,
        "label": AI_ACTIONS[action]["label"],
        "content": content,
    })


@login_required(login_url='login')
@require_POST
def tripChat(request, search_id, flight_date):
    """Proxy chat messages to n8n with this trip's database context attached."""
    search = get_object_or_404(Search, pk=search_id)
    flight = _get_flight_from_search(search, flight_date)

    if not flight:
        return JsonResponse({"success": False, "error": "Flight not found."}, status=404)

    try:
        body = json.loads(request.body)
        message = (body.get("message") or "").strip()
        session_id = body.get("session_id") or (
            f"trip-{search_id}-{flight_date}-u{request.user.id}"
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    if not message:
        return JsonResponse({"success": False, "error": "Message is required."}, status=400)

    trip_context = build_trip_chat_context(search, flight)

    try:
        content = send_n8n_message(message, session_id, trip_context)
    except N8nChatError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=502)

    return JsonResponse({
        "success": True,
        "content": content,
        "session_id": session_id,
    })


@csrf_exempt
@require_GET
def botTripContext(request):
    """
    Return saved trip data from the database for the n8n workflow.
    GET /api/bot-trip-context/?search_id=3&flight_date=2026-06-29
    Header: X-Bot-Api-Key: <secret>
    """
    if not _check_bot_api_key(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        search_id = int(request.GET.get("search_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "search_id is required"}, status=400)

    flight_date = request.GET.get("flight_date")
    if not flight_date:
        return JsonResponse({"error": "flight_date is required"}, status=400)

    search = get_object_or_404(Search, pk=search_id)
    flight = _get_flight_from_search(search, flight_date)
    if not flight:
        return JsonResponse({"error": "Flight not found for this search."}, status=404)

    return JsonResponse(build_trip_chat_context(search, flight))


def _check_bot_api_key(request):
    """Simple shared-secret check so only your n8n workflow can call this."""
    sent_key = request.headers.get("X-Bot-Api-Key")
    return sent_key and sent_key == settings.BOT_API_KEY

#this is the bot search endpoint
@csrf_exempt
@require_GET
def botSearch(request):
    """
    JSON search endpoint for the n8n chatbot.
    No login required — protected by a shared API key header instead.

    GET /api/bot-search/?from_city=DAC&to_city=JED&stay_days=10&timespan_to_search=30
    Header: X-Bot-Api-Key: <your secret>
    """
    if not _check_bot_api_key(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    city_departure = request.GET.get("from_city")
    city_arrival = request.GET.get("to_city")

    if not city_departure or not city_arrival:
        return JsonResponse(
            {"error": "from_city and to_city are required"}, status=400
        )

    try:
        stay_days = int(request.GET.get("stay_days", 7))
        timespan = int(request.GET.get("timespan_to_search", 30))
    except (TypeError, ValueError):
        return JsonResponse({"error": "stay_days and timespan_to_search must be integers"}, status=400)

    search = find_cached_search(city_departure, city_arrival, stay_days, timespan)
    data = None

    if search and extract_flight_days(search.api_response or {}):
        data = search.api_response
    elif search:
        search.delete()
        search = None

    if data is None:
        if not ip_can_call_api(request):
            return JsonResponse({
                "error": "rate_limit_exceeded",
                "message": "Search limit reached for this route. Try again later or use a previously searched route.",
            }, status=429)

        try:
            data = get_flight_data(city_departure, city_arrival, timespan)
        except FlightAPIError as exc:
            return JsonResponse({"error": str(exc)}, status=502)

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
        record_api_call(request)

    days = extract_flight_days(data)
    priced_days = [d for d in days if d.get("price") is not None]
    top_results = [
        _normalize_flight(d)
        for d in sorted(priced_days, key=lambda x: x["price"])[:5]
    ]

    results = []
    for flight in top_results:
        depart = datetime.strptime(flight["flight_date"], "%Y-%m-%d").date()
        return_date = depart + timedelta(days=stay_days)
        results.append({
            "date": flight["flight_date"],
            "price": flight["price"],
            "currency": "USD",
            "return_date": str(return_date),
        })

    return JsonResponse({
        "search_id": search.id,
        "from_city": _city_label(city_departure),
        "to_city": _city_label(city_arrival),
        "stay_days": stay_days,
        "results": results,
    })