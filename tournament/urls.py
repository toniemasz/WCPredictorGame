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
    path('matches/auto-update/', views.auto_update_matches_view, name='auto_update_matches'),
    path('matches/<int:match_id>/', views.match_detail_view, name='match_detail'),
    path('forgot-password/', views.password_reset_request_view, name='forgot_password_stage1'),
    path('reset-password/', views.password_reset_confirm_view, name='password_reset_stage2'),
    path('account/email/request/', views.request_email_verification_view, name='request_email_verification'),
    path('account/email/confirm/', views.confirm_email_verification_view, name='confirm_email_verification'),
    # RANKING I PROFILE
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('stats/', views.stats_view, name='stats'),
    path('achievements/', views.achievements_view, name='achievements'),
    path('watchlist/', views.watchlist_view, name='watchlist'),
    path('profile/', views.profile_view, name='my_profile'),
    path('profile/<int:user_id>/', views.profile_view, name='user_profile'),
    path('profile/', views.profile_view, name='profile'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('matches/<int:match_id>/predictions/', views.match_predictions_view, name='match_predictions'),
    path('matches/<int:match_id>/comments/add/', views.add_match_comment_view, name='add_match_comment'),
    path('comments/<int:comment_id>/delete/', views.delete_match_comment_view, name='delete_match_comment'),
    path('comments/<int:comment_id>/react/', views.react_match_comment_view, name='react_match_comment'),
    path('matches/<int:match_id>/watch/', views.update_match_watch_view, name='update_match_watch'),
    path('prediction/<int:match_id>/', views.create_prediction, name='create_prediction'),
    path('country-language/', views.set_country_language_view, name='set_country_language'),
    path('recalculate/', views.recalculate_points_view, name='recalculate_points'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/first-goal/', views.admin_update_first_goal, name='admin_update_first_goal'),
    path('dashboard/admin/import-matches/', views.admin_trigger_import, name='admin_trigger_import'),
    path('dashboard/admin/sync-odds/', views.admin_trigger_odds, name='admin_trigger_odds'),
    path('dashboard/admin/recalculate/', views.admin_trigger_recalculate, name='admin_trigger_recalculate'),
    path('dashboard/admin/add-players/', views.admin_add_players, name='admin_add_players'),
]
