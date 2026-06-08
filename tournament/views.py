from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from tournament.models import Match, Profile, TeamPlayer, BonusUsage
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

from .services.prediction_service import PredictionService
from .services.scoring_service import ScoringService
from tournament.services.bootstrap_service import BootstrapService
from tournament.services.import_service import ImportService
from tournament.services.odds_sync import OddsSync
from tournament.services.scoring_service import ScoringService
from django.contrib.admin.views.decorators import staff_member_required
from tournament.services.player_import_service import PlayerImportService


BONUS_LIMIT = getattr(settings, 'BONUS_LIMIT_PER_STAGE', 2)


def home_view(request):

    return render(
        request,
        "home.html"
    )


@login_required
def match_list(request):
    if Match.objects.count() == 0:
        ImportService.import_matches()

    matches = Match.objects.select_related(
        'home_team', 'away_team'
    ).prefetch_related(
        'home_team__players', 'away_team__players'
    ).order_by("kickoff")

    user_predictions = Prediction.objects.filter(user=request.user)
    pred_dict = {p.match_id: p for p in user_predictions}

    bonus_usages = BonusUsage.objects.filter(user=request.user)
    bonus_dict = {b.stage: b.count for b in bonus_usages}

    matches_by_stage = {}
    for match in matches:
        match.user_prediction = pred_dict.get(match.id)

        used    = bonus_dict.get(match.stage, 0)
        remaining = BONUS_LIMIT - used
        match.bonus_remaining = remaining

        match.is_bonus_locked = (
            remaining <= 0
            and not (match.user_prediction and match.user_prediction.is_doubled)
        )

        match.available_players = (
            list(match.home_team.players.all()) +
            list(match.away_team.players.all())
        )

        if match.stage not in matches_by_stage:
            matches_by_stage[match.stage] = []
        matches_by_stage[match.stage].append(match)

    active_stage = None
    for stage, stage_matches in matches_by_stage.items():
        if any(m.status in ['LIVE', 'SCHEDULED'] for m in stage_matches):
            active_stage = stage
            break

    if not active_stage and matches_by_stage:
        active_stage = list(matches_by_stage.keys())[-1]

    return render(request, "tournament/match_list.html", {
        'rules_explanation': ScoringService.get_rules_explanation(),
        'matches_by_stage':  matches_by_stage,
        'active_stage':      active_stage,
        'bonus_limit':       BONUS_LIMIT,
    })



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
def profile_view(request, user_id=None):
    # Ustalamy, czy użytkownik ogląda siebie, czy profil innego gracza
    if user_id is None:
        target_user = request.user
    else:
        target_user = get_object_or_404(User, pk=user_id)

    profile = get_object_or_404(Profile, user=target_user)

    # Pobieramy mecze i optymalizujemy zapytania SQL pod kątem flag zespołów
    matches = Match.objects.select_related('home_team', 'away_team').order_by("kickoff")

    # Pobieramy typy właściciela oglądanego profilu
    target_predictions = Prediction.objects.filter(user=target_user)
    target_pred_dict = {p.match_id: p for p in target_predictions}

    # Pobieramy typy zalogowanego przeglądającego (do porównania), jeśli oglądamy kogoś innego
    viewer_pred_dict = {}
    if request.user != target_user:
        viewer_predictions = Prediction.objects.filter(user=request.user)
        viewer_pred_dict = {p.match_id: p for p in viewer_predictions}
    else:
        viewer_pred_dict = target_pred_dict

    # Grupowanie meczów po fazie turnieju (tak samo jak w match_list)
    matches_by_stage = {}
    for match in matches:
        match.target_prediction = target_pred_dict.get(match.id)
        match.viewer_prediction = viewer_pred_dict.get(match.id)

        if match.stage not in matches_by_stage:
            matches_by_stage[match.stage] = []
        matches_by_stage[match.stage].append(match)

    # Wyznaczenie aktywnej fazy do domyślnego wyświetlenia karty
    active_stage = None
    for stage, stage_matches in matches_by_stage.items():
        if any(m.status in ['LIVE', 'SCHEDULED'] for m in stage_matches):
            active_stage = stage
            break

    if not active_stage and matches_by_stage:
        active_stage = list(matches_by_stage.keys())[-1]

    return render(
        request,
        "tournament/profile.html",
        {
            "profile": profile,
            "target_user": target_user,
            "matches_by_stage": matches_by_stage,
            "active_stage": active_stage,
        }
    )


@login_required
def create_prediction(request, match_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == "POST":
        data = {
            "predicted_home": request.POST.get("predicted_home"),
            "predicted_away": request.POST.get("predicted_away"),
            "is_doubled": request.POST.get("is_doubled") == "on",
            "predicted_first_team": request.POST.get("predicted_first_team"),
            "predicted_scorer": request.POST.get("predicted_scorer")
        }

        try:
            result = PredictionService.save_prediction(request.user, match_id, data)
            if is_ajax:
                return JsonResponse(result)
            messages.success(request, "Twój typ został zapisany!")
        except ValueError as e:
            if is_ajax:
                return JsonResponse({"status": "error", "message": str(e)}, status=400)
            messages.error(request, str(e))

    return redirect("match_list")

@login_required
def recalculate_points_view(request):
    BootstrapService.initialize_database()
    if not request.user.is_superuser:
        messages.error(request, "Brak uprawnień.")
        return redirect("match_list")

    # Pobieramy tylko te mecze, które mogą mieć wyniki
    matches = Match.objects.filter(status__in=['LIVE', 'FINISHED'])
    count = 0

    for m in matches:
        ScoringService.recalculate_match(m)
        count += 1

    messages.success(request, f"Sukces! Przeliczono punkty dla {count} meczów.")
    return redirect("match_list")


@login_required
def leaderboard_view(request):
    # Pobieramy profile posortowane od największej liczby punktów z optymalizacją zapytania do tabeli User
    profiles = Profile.objects.select_related('user').order_by('-points')
    return render(
        request,
        "tournament/leaderboard.html",
        {"profiles": profiles}
    )

@staff_member_required
def admin_dashboard(request):
    players_missing = TeamPlayer.objects.count() < 1100
    """Główny widok panelu kontrolnego administratora"""
    return render(request, "tournament/admin_dashboard.html",
                  {
                      "players_missing": players_missing
                  })

@staff_member_required
def admin_trigger_import(request):
    """Ręczne wymuszenie pobrania/aktualizacji meczów z Football-Data API"""
    try:
        ImportService.import_matches()
        messages.success(request, "Sukces! Mecze oraz ich statusy (LIVE/FINISHED) zostały pomyślnie zsynchronizowane z API.")
    except Exception as e:
        messages.error(request, f"Błąd podczas integracji z API meczów: {str(e)}")
    return redirect('admin_dashboard')

@staff_member_required
def admin_trigger_odds(request):
    """Ręczne wymuszenie synchronizacji kursów bukmacherskich"""
    try:
        OddsSync.connect_existing_matches()
        OddsSync.sync_odds()
        messages.success(request, "Sukces! Kursy bukmacherskie (1, X, 2) zostały pomyślnie zaktualizowane.")
    except Exception as e:
        messages.error(request, f"Błąd podczas pobierania kursów: {str(e)}")
    return redirect('admin_dashboard')

@staff_member_required
def admin_trigger_recalculate(request):
    """Ręczne wymuszenie przeliczenia punktów za wszystkie typowania"""
    try:
        # Wywołujemy logikę przeliczania punktów z Twojego serwisu scoringowego
        ScoringService.recalculate_all_predictions()
        messages.success(request, "Sukces! Punkty dla wszystkich użytkowników zostały przeliczone na nowo.")
    except Exception as e:
        messages.error(request, f"Błąd podczas przeliczania punktacji: {str(e)}")
    return redirect('admin_dashboard')


@staff_member_required
def admin_add_players(request):
    """Ręczne wymuszenie synchronizacji kursów bukmacherskich"""
    try:
        PlayerImportService.import_players('world_cup_players.json')
        messages.success(request, "Sukces! Dodano nowych graczy.")
    except Exception as e:
        messages.error(request, f"Błąd podczas pobierania kursów: {str(e)}")
    return redirect('admin_dashboard')