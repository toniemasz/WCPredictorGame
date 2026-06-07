# tournament/tests.py
import pytest
from django.utils import timezone
from django.contrib.auth.models import User

from tournament.models import Team, Match, Prediction
from tournament.services.scoring_service import ScoringService


# --- FIXTURES (Przygotowanie danych) ---

@pytest.fixture
def test_user(db):
    """Tworzy testowego użytkownika."""
    return User.objects.create_user(username='tester', password='123')


@pytest.fixture
def teams(db):
    """Tworzy dwie testowe drużyny."""
    team_pl = Team.objects.create(name='Poland', code='POL')
    team_de = Team.objects.create(name='Germany', code='GER')
    return team_pl, team_de


@pytest.fixture
def finished_match(db, teams):
    """Tworzy zakończony mecz Polska 2:1 Niemcy."""
    team_pl, team_de = teams
    return Match.objects.create(
        home_team=team_pl,
        away_team=team_de,
        kickoff=timezone.now() - timezone.timedelta(days=1),
        status='FINISHED',
        home_score=2,
        away_score=1,
        stage='GROUP_STAGE'
    )


# --- TESTY ---

@pytest.mark.django_db
def test_exact_score(test_user, finished_match):
    """Gracz trafia idealny wynik 2:1 (powinien dostać 3 punkty)"""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=2, predicted_away=1
    )

    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()

    assert prediction.points == 3


@pytest.mark.django_db
def test_correct_goal_difference(test_user, finished_match):
    """Gracz trafia zwycięzcę oraz różnicę bramek, np. 3:2 (powinien dostać 2 punkty)"""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=3, predicted_away=2
    )

    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()

    assert prediction.points == 2


@pytest.mark.django_db
def test_correct_winner_only(test_user, finished_match):
    """Gracz trafia tylko wygraną Polski, np. 3:0 (powinien dostać 1 punkt)"""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=3, predicted_away=0
    )

    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()

    assert prediction.points == 1


@pytest.mark.django_db
def test_wrong_prediction(test_user, finished_match):
    """Gracz obstawia wygraną Niemiec, np. 0:2 (powinien dostać 0 punktów)"""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=0, predicted_away=2
    )

    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()

    assert prediction.points == 0


@pytest.mark.django_db
def test_doubled_points(test_user, finished_match):
    """Gracz trafia idealny wynik 2:1 i użył podwojenia (powinien dostać 6 punktów)"""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=2, predicted_away=1, is_doubled=True
    )

    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()

    assert prediction.points == 6


@pytest.mark.django_db
def test_profile_total_points_updated(test_user, finished_match):
    """Sprawdzenie, czy metoda aktualizuje łączne punkty na profilu gracza."""
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match, predicted_home=2, predicted_away=1
    )

    ScoringService.calculate_points_for_match(finished_match)
    test_user.profile.refresh_from_db()

    assert test_user.profile.points == 3