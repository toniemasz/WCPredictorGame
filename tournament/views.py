from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect

from tournament.models import MatchComment, TeamPlayer
from tournament.services.account_security_service import AccountSecurityService
from tournament.services.achievement_service import AchievementService
from tournament.services.admin_match_service import AdminMatchService
from tournament.services.bootstrap_service import BootstrapService
from tournament.services.comment_service import MatchCommentService
from tournament.services.import_service import ImportService
from tournament.services.home_service import HomePageService
from tournament.services.match_auto_update_service import MatchAutoUpdateService
from tournament.services.match_service import MatchListService
from tournament.services.odds_sync import OddsSync
from tournament.services.player_import_service import PlayerImportService
from tournament.services.profile_service import ProfileService
from tournament.services.scoring_service import ScoringService
from tournament.services.stats_service import StatsService
from tournament.services.team_name_service import TeamNameService
from tournament.services.watch_service import MatchWatchService
from .services.prediction_service import PredictionService


def custom_error_view(request, exception=None, status_code=500):
    response = render(
        request,
        "errors/error.html",
        {"status_code": status_code},
        status=status_code,
    )
    response.headers["X-Custom-Error-Page"] = "1"
    return response


def bad_request_view(request, exception):
    return custom_error_view(request, exception, 400)


def permission_denied_view(request, exception):
    return custom_error_view(request, exception, 403)


def page_not_found_view(request, exception):
    return custom_error_view(request, exception, 404)


def server_error_view(request):
    return custom_error_view(request, status_code=500)


def csrf_failure_view(request, reason=""):
    return custom_error_view(request, status_code=403)


PASSWORD_RESET_NOTICE_SESSION_KEY = "password_reset_notice"


def _password_reset_notice(level, text):
    return {"level": level, "text": text}


def _store_password_reset_notice(request, level, text):
    request.session[PASSWORD_RESET_NOTICE_SESSION_KEY] = _password_reset_notice(level, text)


def _pop_password_reset_notice(request):
    return request.session.pop(PASSWORD_RESET_NOTICE_SESSION_KEY, None)


def home_view(request):
    return render(
        request,
        "home.html",
        HomePageService.get_context(
            request.user,
            TeamNameService.get_language(request),
        )
    )


@login_required
def match_list(request):
    context = MatchListService.get_match_list_context(
        request.user,
        TeamNameService.get_language(request),
    )
    return render(request, "tournament/match_list.html", context)


@login_required
def auto_update_matches_view(request):
    result = MatchAutoUpdateService.check_and_update_matches()
    status_code = 500 if result["status"] == "error" else 200
    return JsonResponse(result, status=status_code)


@login_required
def match_predictions_view(request, match_id):
    try:
        context = MatchListService.get_public_predictions_context(
            match_id,
            TeamNameService.get_language(request),
        )
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("match_list")

    return render(request, "tournament/match_predictions.html", context)


def match_detail_view(request, match_id):
    context = MatchListService.get_match_detail_context(
        match_id,
        request.user,
        TeamNameService.get_language(request),
    )
    return render(request, "tournament/match_detail.html", context)


@login_required
@require_POST
def add_match_comment_view(request, match_id):
    try:
        MatchCommentService.add_comment(
            request.user,
            match_id,
            request.POST.get("content"),
        )
        messages.success(request, "Komentarz został dodany.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect(f"{reverse('match_detail', args=[match_id])}#comments")


@login_required
@require_POST
def delete_match_comment_view(request, comment_id):
    try:
        comment = MatchCommentService.delete_comment(request.user, comment_id)
        messages.success(request, "Komentarz został usunięty.")
        return redirect(f"{reverse('match_detail', args=[comment.match_id])}#comments")
    except PermissionError as error:
        messages.error(request, str(error))
        return redirect("match_list")


@login_required
@require_POST
def react_match_comment_view(request, comment_id):
    match_id = request.POST.get("match_id")
    try:
        reaction = MatchCommentService.toggle_reaction(
            request.user,
            comment_id,
            request.POST.get("reaction"),
        )
        messages.success(
            request,
            "Reakcja została zapisana." if reaction else "Reakcja została cofnięta.",
        )
    except ValueError as error:
        messages.error(request, str(error))

    if not match_id:
        match_id = MatchComment.objects.get(pk=comment_id).match_id

    return redirect(f"{reverse('match_detail', args=[match_id])}#comments")


@login_required
def stats_view(request):
    context = StatsService.get_stats_context(
        request.user,
        request.GET.get("stage"),
        TeamNameService.get_language(request),
    )
    return render(request, "tournament/stats.html", context)


@login_required
def watchlist_view(request):
    return render(
        request,
        "tournament/watchlist.html",
        MatchWatchService.get_watch_context(
            request.user,
            TeamNameService.get_language(request),
        ),
    )


@login_required
def achievements_view(request):
    return render(
        request,
        "tournament/achievements.html",
        AchievementService.get_page_context(request.user),
    )


@login_required
@require_POST
def update_match_watch_view(request, match_id):
    try:
        MatchWatchService.update_entry(
            request.user,
            match_id,
            request.POST.get("action"),
        )
        messages.success(request, "Lista meczów do obejrzenia została zaktualizowana.")
    except ValueError as error:
        messages.error(request, str(error))

    next_url = request.POST.get("next") or reverse("watchlist")
    return redirect(next_url)


@require_POST
def set_country_language_view(request):
    try:
        TeamNameService.set_language(request, request.POST.get("language"))
        messages.success(request, "Zmieniono język nazw krajów.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect(request.POST.get("next") or "home")


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


def password_reset_request_view(request):
    notice = None
    email_value = ""

    if request.method == 'POST':
        email = request.POST.get("email", "")
        return_to_confirm = request.POST.get("next") == reverse("password_reset_stage2")
        try:
            normalized_email = AccountSecurityService.normalize_email(email)
            AccountSecurityService.request_password_reset(normalized_email)
            request.session[
                AccountSecurityService.PASSWORD_RESET_SESSION_EMAIL
            ] = normalized_email
            if AccountSecurityService.uses_console_email_backend():
                notice = _password_reset_notice(
                    "warning",
                    "Kod został wygenerowany, ale aplikacja używa konsolowego backendu e-mail. Ustaw SMTP, żeby wiadomość trafiła do skrzynki.",
                )
            else:
                notice = _password_reset_notice(
                    "success",
                    "Jeżeli ten adres jest przypisany do konta, wysłaliśmy kod do zmiany hasła.",
                )
            _store_password_reset_notice(request, notice["level"], notice["text"])
            return redirect("password_reset_stage2")
        except ValueError as error:
            notice = _password_reset_notice("error", str(error))
            email_value = email
            if return_to_confirm:
                _store_password_reset_notice(request, notice["level"], notice["text"])
                return redirect("password_reset_stage2")

    return render(
        request,
        'registration/forgot_password_troll.html',
        {
            "email": email_value,
            "notice": notice,
        },
    )


def password_reset_confirm_view(request):
    email = request.session.get(AccountSecurityService.PASSWORD_RESET_SESSION_EMAIL, "")
    notice = _pop_password_reset_notice(request)

    if request.method == 'POST':
        email = request.POST.get("email") or email
        try:
            AccountSecurityService.reset_password(
                email,
                request.POST.get("code"),
                request.POST.get("new_password"),
                request.POST.get("password_confirm"),
            )
            request.session.pop(AccountSecurityService.PASSWORD_RESET_SESSION_EMAIL, None)
            messages.success(request, "Hasło zostało zmienione. Możesz się zalogować.")
            return redirect("login")
        except ValueError as error:
            notice = _password_reset_notice("error", str(error))

    return render(
        request,
        'registration/password_reset_real.html',
        {
            "email": email,
            "notice": notice,
        },
    )


@login_required
@require_POST
def request_email_verification_view(request):
    next_url = request.POST.get("next") or reverse("profile")
    remember_choice = request.POST.get("remember_missing_email_warning") == "on"
    email = (request.POST.get("email") or "").strip()

    if remember_choice:
        AccountSecurityService.remember_missing_email_warning(request)

    if not email:
        if remember_choice:
            messages.info(request, "Zapamiętaliśmy wybór. Ostrzeżenie nie będzie już pokazywane w tej sesji.")
        else:
            messages.error(request, "Podaj adres e-mail albo zaznacz zapamiętanie wyboru.")
        response = redirect(next_url)
        if remember_choice:
            AccountSecurityService.apply_missing_email_warning_cookie(response)
        return response

    try:
        pending_email = AccountSecurityService.start_email_change(request.user, email)
        if AccountSecurityService.uses_console_email_backend():
            messages.warning(
                request,
                "Kod został wygenerowany, ale aplikacja używa konsolowego backendu e-mail. Ustaw SMTP, żeby wiadomość trafiła do skrzynki.",
            )
        else:
            messages.success(
                request,
                f"Wysłaliśmy kod potwierdzający na {pending_email}. Podaj go w profilu, aby zapisać e-mail.",
            )
        response = redirect("profile")
        if remember_choice:
            AccountSecurityService.apply_missing_email_warning_cookie(response)
        return response
    except ValueError as error:
        messages.error(request, str(error))
        response = redirect(next_url)
        if remember_choice:
            AccountSecurityService.apply_missing_email_warning_cookie(response)
        return response


@login_required
@require_POST
def confirm_email_verification_view(request):
    try:
        AccountSecurityService.confirm_email_change(
            request.user,
            request.POST.get("code"),
        )
        messages.success(request, "Adres e-mail został potwierdzony i zapisany.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect("profile")

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
                      "players_missing": players_missing,
                      "first_goal_context": AdminMatchService.get_first_goal_context(
                          TeamNameService.get_language(request),
                      ),
                  })


@staff_member_required
@require_POST
def admin_update_first_goal(request):
    try:
        AdminMatchService.update_first_goal(
            request.POST.get("match_id"),
            request.POST.get("first_scoring_team"),
            request.POST.get("first_scorer"),
        )
        messages.success(request, "Pierwszy gol został zapisany i punkty przeliczone.")
    except Exception as error:
        messages.error(request, f"Nie udało się zapisać pierwszego gola: {error}")

    return redirect("admin_dashboard")

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
