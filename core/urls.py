from django.urls import path
from . import views


urlpatterns = [
    path('', views.searchView, name='home'),
    path('search/', views.searchResults, name='search_results'),
]
