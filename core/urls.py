from django.urls import path
from . import views


urlpatterns = [
    # Home page
    path('', views.searchView, name='home'),
    
    # Authentication
    path('register/', views.registerView, name='register'),
    path('login/', views.loginView, name='login'),
    path('logout/', views.logoutView, name='logout'),
    
    # Search functionality
    path('search/', views.searchResults, name='search_results'),
    path(
        'search/flight/<int:search_id>/<str:flight_date>/',
        views.flightDetail,
        name='flight_detail',
    ),
    path("api/bot-search/", views.botSearch, name="bot_search"),
    path("api/bot-trip-context/", views.botTripContext, name="bot_trip_context"),
    path(
        'search/flight/<int:search_id>/<str:flight_date>/ai/',
        views.aiAction,
        name='ai_action',
    ),
    path(
        'search/flight/<int:search_id>/<str:flight_date>/chat/',
        views.tripChat,
        name='trip_chat',
    ),
]
