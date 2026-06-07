from django.urls import path

from .views import (
    match_list,
    register_view,
    login_view,
    logout_view,
    profile_view, home_view, create_prediction, recalculate_points_view
)

urlpatterns = [

    path(
        "",
        home_view,
        name="home"
    ),
    path(
        "matches/",
        match_list,
        name="match_list"
    ),

    path(
        "register/",
        register_view,
        name="register"
    ),

    path(
        "login/",
        login_view,
        name="login"
    ),

    path(
        "logout/",
        logout_view,
        name="logout"
    ),

    path(
        "profile/",
        profile_view,
        name="profile"
    ),
path(
        "recalculate/",
        recalculate_points_view,
        name="recalculate_points"
    ),
    path(
        "predict/<int:match_id>/",
        create_prediction,
        name="create_prediction"
    ),
]