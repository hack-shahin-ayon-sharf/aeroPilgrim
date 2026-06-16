from django.contrib import admin
from .models import Search, SearchRateLimit

admin.site.register(Search)
admin.site.register(SearchRateLimit)