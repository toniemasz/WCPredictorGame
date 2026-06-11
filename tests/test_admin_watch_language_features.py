import pytest
from django.core import mail
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from tournament.models import MatchWatch, TeamPlayer
from tournament.services.admin_match_service import AdminMatchService
from tournament.services.match_service import MatchListService
from tournament.services.scoring_service import ScoringService
from tournament.services.team_name_service import TeamNameService
from tournament.services.watch_service import MatchWatchService


@pytest.mark.django_db
def test_next_unfinished_round_is_default_active_stage(user, make_match):
    make_match(
        stage="Runda 1",
        status="FINISHED",
        home_score=1,
        away_score=0,
    )
    make_match(
        stage="Runda 2",
        status="SCHEDULED",
        home_score=None,
        away_score=None,
    )

    context = MatchListService.get_match_list_context(user)
    active_stage = next(stage for stage in context["stage_groups"] if stage["is_active"])

    assert active_stage["name"] == "Runda 2"


@pytest.mark.django_db
def test_player_display_label_contains_position_and_nationality(teams):
    player = TeamPlayer.objects.create(
        api_player_id=123,
        team=teams[0],
        name="Jan Testowy",
        position="FW",
        nationality="Polska",
    )

    assert player.display_label == "Jan Testowy · FW · Polska"


@pytest.mark.django_db
def test_admin_service_lists_live_finished_or_result_open_matches(make_match):
    scheduled = make_match(stage="Plan")
    live = make_match(stage="Live", status="LIVE", first_scoring_team=None, first_scorer="")
    finished = make_match(
        stage="Koniec",
        status="FINISHED",
        home_score=1,
        away_score=0,
        first_scoring_team=None,
        first_scorer="",
    )
    score_open = make_match(
        stage="Wynik",
        status="SCHEDULED",
        home_score=1,
        away_score=None,
        first_scoring_team=None,
        first_scorer="",
    )
    complete = make_match(
        stage="Gotowy",
        status="FINISHED",
        home_score=1,
        away_score=0,
        first_scoring_team="HOME",
        first_scorer="Lewandowski",
    )

    matches = list(AdminMatchService.get_first_goal_matches())

    assert live in matches
    assert finished in matches
    assert score_open in matches
    assert scheduled not in matches
    assert complete not in matches


@pytest.mark.django_db
def test_admin_service_updates_first_goal_fields(make_match, teams):
    match = make_match(
        status="FINISHED",
        home_score=2,
        away_score=0,
        first_scoring_team=None,
        first_scorer="",
    )
    TeamPlayer.objects.create(
        api_player_id=777,
        team=teams[1],
        name="Lista Strzelec",
        position="FW",
        nationality="Niemcy",
    )

    updated = AdminMatchService.update_first_goal(match.id, "AWAY", "Lista Strzelec")

    updated.refresh_from_db()
    assert updated.first_scoring_team == "AWAY"
    assert updated.first_scorer == "Lista Strzelec"
    assert updated not in list(AdminMatchService.get_first_goal_matches())


@pytest.mark.django_db
def test_admin_service_rejects_first_scorer_outside_match_player_list(make_match):
    match = make_match(status="FINISHED", home_score=2, away_score=0)

    with pytest.raises(ValueError, match="listy zawodników"):
        AdminMatchService.update_first_goal(match.id, "AWAY", "Spoza listy")


@pytest.mark.django_db
def test_admin_service_sets_no_scorer_when_no_goals_selected(make_match):
    match = make_match(
        status="FINISHED",
        home_score=0,
        away_score=0,
        first_scoring_team=None,
        first_scorer="",
    )

    updated = AdminMatchService.update_first_goal(match.id, "NONE", "Nie powinien zostać")

    assert updated.first_scoring_team == "NONE"
    assert updated.first_scorer == ScoringService.NO_SCORER
    assert updated not in list(AdminMatchService.get_first_goal_matches())


@pytest.mark.django_db
def test_admin_service_rejects_no_scorer_with_scoring_team(make_match):
    match = make_match(status="FINISHED", home_score=1, away_score=0)

    with pytest.raises(ValueError, match="Brak strzelca"):
        AdminMatchService.update_first_goal(
            match.id,
            "HOME",
            ScoringService.NO_SCORER,
        )


@pytest.mark.django_db
def test_admin_first_goal_context_contains_match_teams_and_full_player_list(make_match, teams):
    match = make_match(
        status="FINISHED",
        home_score=2,
        away_score=0,
        first_scoring_team=None,
        first_scorer="",
    )
    TeamPlayer.objects.create(
        api_player_id=778,
        team=teams[0],
        name="Domowy Gracz",
        position="MF",
        nationality="Polska",
    )
    TeamPlayer.objects.create(
        api_player_id=779,
        team=teams[1],
        name="Gość Gracz",
        position="FW",
        nationality="Niemcy",
    )

    context = AdminMatchService.get_first_goal_context()
    option = next(item for item in context["matches"] if item["id"] == match.id)

    assert option["team_choices"][1]["label"] == "Polska"
    assert option["team_choices"][2]["label"] == "Niemcy"
    assert option["no_scorer_value"] == ScoringService.NO_SCORER
    assert {player["value"] for player in option["player_choices"]} == {
        "Domowy Gracz",
        "Gość Gracz",
    }


@pytest.mark.django_db
def test_admin_dashboard_renders_pending_first_goal_matches_as_cards(client, make_match):
    staff = User.objects.create_user(
        username="admin",
        password="pass",
        is_staff=True,
    )
    pending = make_match(
        stage="Do uzupełnienia",
        status="FINISHED",
        home_score=1,
        away_score=0,
        first_scoring_team=None,
        first_scorer="",
    )
    make_match(
        stage="Gotowy",
        status="FINISHED",
        home_score=1,
        away_score=0,
        first_scoring_team="HOME",
        first_scorer="Lewandowski",
    )
    client.force_login(staff)

    response = client.get(reverse("admin_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert content.count('class="first-goal-card wc-card space-y-4"') == 1
    assert f'name="match_id" value="{pending.id}"' in content
    assert "Do uzupełnienia" in content
    assert "Gotowy" not in content
    assert 'id="first-goal-match"' not in content


@pytest.mark.django_db
def test_admin_dashboard_renders_smtp_diagnostics(client):
    staff = User.objects.create_user(
        username="admin",
        password="pass",
        email="admin@example.com",
        is_staff=True,
    )
    client.force_login(staff)

    response = client.get(reverse("admin_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "SMTP i e-mail" in content
    assert "Wyślij test SMTP" in content


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_admin_test_smtp_sends_test_email(client):
    staff = User.objects.create_user(
        username="admin",
        password="pass",
        email="admin@example.com",
        is_staff=True,
    )
    client.force_login(staff)

    response = client.post(
        reverse("admin_test_smtp"),
        {"recipient": "target@example.com"},
    )

    assert response.status_code == 302
    assert response.url == reverse("admin_dashboard")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["target@example.com"]


@pytest.mark.django_db
@override_settings(EMAIL_HOST_PASSWORD="hidden-password")
def test_admin_test_smtp_shows_safe_error_details(client, monkeypatch):
    staff = User.objects.create_user(
        username="admin",
        password="pass",
        email="admin@example.com",
        is_staff=True,
    )
    client.force_login(staff)

    def broken_send_mail(*args, **kwargs):
        raise RuntimeError("smtp unavailable hidden-password")

    monkeypatch.setattr(
        "tournament.services.account_security_service.send_mail",
        broken_send_mail,
    )

    response = client.post(
        reverse("admin_test_smtp"),
        {"recipient": "target@example.com"},
        follow=True,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Test SMTP nieudany: RuntimeError: smtp unavailable [ukryte]" in content
    assert "hidden-password" not in content


@pytest.mark.django_db
def test_watch_service_adds_marks_and_removes_match(user, future_match):
    entry = MatchWatchService.update_entry(user, future_match.id, "add")

    assert entry.want_to_watch is True
    assert entry.watched is False

    entry = MatchWatchService.update_entry(user, future_match.id, "watched")
    assert entry.want_to_watch is True
    assert entry.watched is True

    entry = MatchWatchService.update_entry(user, future_match.id, "remove")
    assert entry.want_to_watch is False
    assert entry.watched is False


@pytest.mark.django_db
def test_watchlist_view_uses_selected_country_language(client, user, future_match):
    MatchWatch.objects.create(user=user, match=future_match)
    client.force_login(user)
    session = client.session
    session[TeamNameService.SESSION_KEY] = TeamNameService.LANGUAGE_EN
    session.save()

    response = client.get(reverse("watchlist"))

    content = response.content.decode()
    assert "Poland" in content
    assert "Germany" in content
    assert "Polska" not in content
    assert "Niemcy" not in content


@pytest.mark.django_db
def test_country_language_post_updates_session(client):
    response = client.post(
        reverse("set_country_language"),
        {"language": "en", "next": reverse("home")},
    )

    assert response.status_code == 302
    assert client.session[TeamNameService.SESSION_KEY] == "en"


@pytest.mark.django_db
def test_match_list_context_uses_english_country_names(user, future_match):
    context = MatchListService.get_match_list_context(user, country_language="en")
    match = context["stage_groups"][0]["matches"][0]

    assert match.home_team.display_name == "Poland"
    assert match.away_team.display_name == "Germany"
