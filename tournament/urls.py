from django.urls import path

from .views import (
    match_list,
    register_view,
    login_view,
    logout_view,
    profile_view, home_view, create_prediction, recalculate_points_view
)

# tournament/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('matches/', views.match_list, name='match_list'),

    # RANKING I PROFILE
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('profile/', views.profile_view, name='my_profile'),
    path('profile/<int:user_id>/', views.profile_view, name='user_profile'),

    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('prediction/<int:match_id>/', views.create_prediction, name='create_prediction'),
    path('recalculate/', views.recalculate_points_view, name='recalculate_points'),
]