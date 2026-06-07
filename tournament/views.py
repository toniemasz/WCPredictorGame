from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from tournament.models import Match
from tournament.services.import_service import ImportService
from tournament.forms import RegisterForm
from django.contrib.auth.decorators import login_required

def home_view(request):

    return render(
        request,
        "home.html"
    )

@login_required
def match_list(request):

    if Match.objects.count() == 0:
        ImportService.import_matches()

    matches = Match.objects.order_by("kickoff")

    return render(
        request,
        "tournament/match_list.html",
        {
            "matches": matches
        }
    )


def register_view(request):

    if request.method == "POST":

        form = RegisterForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"]
            )

            avatar = form.cleaned_data.get("avatar")

            if avatar:
                user.profile.avatar = avatar
                user.profile.save()

            login(request, user)

            return redirect("match_list")

    else:

        form = RegisterForm()

    return render(
        request,
        "registration/register.html",
        {
            "form": form
        }
    )


def login_view(request):

    if request.method == "POST":

        form = AuthenticationForm(
            request,
            data=request.POST
        )

        if form.is_valid():

            login(
                request,
                form.get_user()
            )

            return redirect("match_list")

    else:

        form = AuthenticationForm()

    return render(
        request,
        "registration/login.html",
        {
            "form": form
        }
    )

@login_required
def logout_view(request):

    logout(request)

    return redirect("match_list")

@login_required
def profile_view(request):

    return render(
        request,
        "profile.html"
    )