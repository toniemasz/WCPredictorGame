from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect

from tournament.models import TeamPlayer
from tournament.services.bootstrap_service import BootstrapService
from tournament.services.import_service import ImportService
from tournament.services.home_service import HomePageService
from tournament.services.match_service import MatchListService
from tournament.services.odds_sync import OddsSync
from tournament.services.player_import_service import PlayerImportService
from tournament.services.profile_service import ProfileService
from tournament.services.scoring_service import ScoringService
from .services.prediction_service import PredictionService


def home_view(request):

    return render(
        request,
        "home.html",
        HomePageService.get_context()
    )


@login_required
def match_list(request):
    context = MatchListService.get_match_list_context(request.user)
    return render(request, "tournament/match_list.html", context)


@login_required
def match_predictions_view(request, match_id):
    try:
        context = MatchListService.get_public_predictions_context(match_id)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("match_list")

    return render(request, "tournament/match_predictions.html", context)


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')

        # TWARDA WALIDACJA NA BACKENDZIE
        if password != password_confirm:
            # Tworzymy słownik z błędami, żeby dopasować się do Twojego HTML {% if form.errors %}
            # Możesz też użyć wbudowanego systemu messages
            fake_form_errors = {'password': ['Hasła nie są identyczne!']}
            return render(request, 'registration/register.html', {'form': {'errors': fake_form_errors}})

        # Dopiero gdy backend potwierdzi, że hasła są identyczne, uderzamy do bazy
        if not User.objects.filter(username=username).exists():
            User.objects.create_user(username=username, email=email, password=password)
            return redirect('login')
        else:
            fake_form_errors = {'username': ['Taki użytkownik już istnieje.']}
            return render(request, 'registration/register.html', {'form': {'errors': fake_form_errors}})

    return render(request, 'registration/register.html')


@login_required
def profile_view(request, user_id=None):
    target_user = ProfileService.get_target_user(request.user, user_id)

    if request.method == 'POST':
        try:
            if ProfileService.update_profile(request.user, target_user, request.POST):
                messages.success(request, 'Profil został zaktualizowany!')
                return redirect('profile')
        except ValueError as error:
            messages.error(request, str(error))

    context = ProfileService.get_profile_context(request.user, target_user=target_user)
    return render(request, 'tournament/profile.html', context)


def forgot_password_troll_view(request):
    if request.method == 'POST':
        # Pobieramy odpowiedź, usuwamy białe znaki i zamieniamy na małe litery
        answer = request.POST.get('creator_name', '').strip().lower()

        # Sprawdzamy warianty (tomasz, tomek itp.)
        if answer in ['tomasz', 'tomek']:
            # Zapisujemy w sesji, że użytkownik przeszedł test!
            request.session['passed_troll_gate'] = True
            return redirect('password_reset_stage2')
        else:
            # Zła odpowiedź - odrzucamy
            return render(request, 'registration/forgot_password_troll.html', {
                'error': 'Pudło! Jak możesz nie znać imienia swojego stwórcy?! Spróbuj ponownie.'
            })

    # Domyślny GET (wyświetlenie formularza)
    return render(request, 'registration/forgot_password_troll.html', {'error': ''})


def password_reset_stage2_view(request):
    # BACKENDOWY STRAŻNIK: Sprawdzamy, czy użytkownik przeszedł Etap 1
    if not request.session.get('passed_troll_gate'):
        # Jeśli nie, wywalamy go z powrotem na śmieszną stronę
        return redirect('forgot_password_stage1')

    if request.method == 'POST':
        username = request.POST.get('username')
        new_password = request.POST.get('new_password')

        try:
            user = User.objects.get(username=username)
            user.set_password(new_password)  # Bezpieczne haszowanie hasła w Django
            user.save()

            # Czyścimy sesję po udanej zmianie, żeby nie mógł tu wrócić bez podania imienia
            del request.session['passed_troll_gate']

            return redirect('login')  # Przekierowanie do logowania po sukcesie
        except User.DoesNotExist:
            return render(request, 'registration/password_reset_real.html', {
                'error': 'Taki użytkownik nie istnieje!'
            })

    return render(request, 'registration/password_reset_real.html')

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

    count = ScoringService.recalculate_finished_matches()

    messages.success(request, f"Sukces! Przeliczono punkty dla {count} meczów.")
    return redirect("match_list")


@login_required
def leaderboard_view(request):
    return render(
        request,
        "tournament/leaderboard.html",
        {"profiles": ProfileService.get_leaderboard_profiles()}
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
        count = ScoringService.recalculate_finished_matches()
        messages.success(request, f"Sukces! Punkty dla {count} meczów zostały przeliczone na nowo.")
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
