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
    path('forgot-password/', views.forgot_password_troll_view, name='forgot_password_stage1'),

    path('reset-password/', views.password_reset_stage2_view, name='password_reset_stage2'),
    # RANKING I PROFILE
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('profile/', views.profile_view, name='my_profile'),
    path('profile/<int:user_id>/', views.profile_view, name='user_profile'),
    path('profile/', views.profile_view, name='profile'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('prediction/<int:match_id>/', views.create_prediction, name='create_prediction'),
    path('recalculate/', views.recalculate_points_view, name='recalculate_points'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/import-matches/', views.admin_trigger_import, name='admin_trigger_import'),
    path('dashboard/admin/sync-odds/', views.admin_trigger_odds, name='admin_trigger_odds'),
    path('dashboard/admin/recalculate/', views.admin_trigger_recalculate, name='admin_trigger_recalculate'),
    path('dashboard/admin/add-players/', views.admin_add_players, name='admin_add_players'),
]