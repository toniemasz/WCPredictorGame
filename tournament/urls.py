from django.urls import path
from .views import match_list

urlpatterns = [
    path("", match_list, name="match_list"),
]