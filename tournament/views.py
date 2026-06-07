from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from tournament.models import Match
from tournament.services.import_service import ImportService
from tournament.forms import RegisterForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Prediction
from .forms import PredictionForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from tournament.models import Match, Prediction
from tournament.services.import_service import ImportService
from django.http import JsonResponse


def home_view(request):

    return render(
        request,
        "home.html"
    )


def match_list(request):
    if Match.objects.count() == 0:
        ImportService.import_matches()

    matches = Match.objects.order_by("kickoff")
    user_predictions = Prediction.objects.filter(user=request.user)
    pred_dict = {p.match_id: p for p in user_predictions}

    # 1. Sprawdzamy, w których fazach (rundach) użytkownik ma ZABLOKOWANY Bonus x2
    # Bonus jest zablokowany, jeśli mecz z is_doubled=True już się rozpoczął.
    locked_bonuses_stages = set(
        Prediction.objects.filter(
            user=request.user,
            is_doubled=True,
            match__kickoff__lte=timezone.now()
        ).values_list('match__stage', flat=True)
    )

    # 2. Grupowanie meczów po fazie turnieju
    matches_by_stage = {}
    for match in matches:
        match.user_prediction = pred_dict.get(match.id)
        # Przekazujemy do szablonu informację, czy bonus w tej rundzie przepadł/został użyty
        match.is_bonus_locked = match.stage in locked_bonuses_stages

        if match.stage not in matches_by_stage:
            matches_by_stage[match.stage] = []
        matches_by_stage[match.stage].append(match)

    # 3. Ustalenie "aktualnej" rundy do wyświetlenia na start
    active_stage = None
    for stage, stage_matches in matches_by_stage.items():
        # Bierzemy pierwszą fazę, w której są zaplanowane lub trwające mecze
        if any(m.status in ['LIVE', 'SCHEDULED'] for m in stage_matches):
            active_stage = stage
            break

    # Jeśli wszystkie mecze na świecie się skończyły, pokaż ostatnią fazę
    if not active_stage and matches_by_stage:
        active_stage = list(matches_by_stage.keys())[-1]

    return render(
        request,
        "tournament/match_list.html",
        {
            "matches_by_stage": matches_by_stage,
            "active_stage": active_stage,
        }
    )


def register_view(request):
    # Jeśli użytkownik jest już zalogowany, odeślij go do meczów
    if request.user.is_authenticated:
        return redirect("match_list")

    if request.method == "POST":
        form = RegisterForm(request.POST, request.FILES)
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

    return render(request, "registration/register.html", {"form": form})


def login_view(request):
    # Jeśli użytkownik jest już zalogowany, odeślij go do meczów
    if request.user.is_authenticated:
        return redirect("match_list")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("match_list")
    else:
        form = AuthenticationForm()

    return render(request, "registration/login.html", {"form": form})

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


@login_required
def create_prediction(request, match_id):
    match = get_object_or_404(Match, pk=match_id)

    # Sprawdzamy, czy to zapytanie AJAX (z JavaScriptu)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if timezone.now() >= match.kickoff:
        msg = "Ten mecz już się rozpoczął! Nie możesz zmienić typu."
        if is_ajax: return JsonResponse({"status": "error", "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("match_list")

    if request.method == "POST":
        home = request.POST.get("predicted_home")
        away = request.POST.get("predicted_away")
        is_doubled = request.POST.get("is_doubled") == "on"

        # Nie zapisujemy pustych wartości
        if home == "" or away == "" or home is None or away is None:
            if is_ajax: return JsonResponse({"status": "error", "message": "Wpisz obie wartości"})
            return redirect("match_list")

        if is_doubled:
            existing_double = Prediction.objects.filter(
                user=request.user,
                match__stage=match.stage,
                is_doubled=True
            ).exclude(match=match).first()

            if existing_double:
                if existing_double.match.kickoff <= timezone.now():
                    msg = f"Twój Bonus x2 w rundzie {match.stage} jest zamrożony na meczu {existing_double.match.home_team} vs {existing_double.match.away_team}!"
                    if is_ajax: return JsonResponse({"status": "error", "message": msg}, status=400)
                    messages.error(request, msg)
                    return redirect("match_list")
                else:
                    existing_double.is_doubled = False
                    existing_double.save(update_fields=['is_doubled'])

        # Zapis typu
        Prediction.objects.update_or_create(
            user=request.user,
            match=match,
            defaults={
                "predicted_home": home,
                "predicted_away": away,
                "is_doubled": is_doubled
            }
        )

        # Sukces! Zwracamy odpowiedź dla JavaScriptu
        if is_ajax:
            return JsonResponse({"status": "success"})

        messages.success(request, "Twój typ został zapisany!")

    return redirect("match_list")