import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal

from tournament.models import Team, Match, Prediction
from tournament.services.scoring_service import ScoringService

@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='tester', password='123')

@pytest.fixture
def teams(db):
    team_pl = Team.objects.create(name='Poland', code='POL')
    team_de = Team.objects.create(name='Germany', code='GER')
    return team_pl, team_de

@pytest.fixture
def finished_match(db, teams):
    team_pl, team_de = teams
    return Match.objects.create(
        home_team=team_pl,
        away_team=team_de,
        kickoff=timezone.now() - timezone.timedelta(days=1),
        status='FINISHED',
        home_score=2,
        away_score=1,
        stage='GROUP_STAGE',
        # Pola kursów
        home_odds=Decimal('4.20'),
        draw_odds=Decimal('3.00'),
        away_odds=Decimal('1.70'),
        # Pola strzelców
        first_scoring_team='HOME',
        goalscorers='Lewandowski, Milik, Müller'
    )

@pytest.mark.django_db
def test_exact_score_with_perfect_match(test_user, finished_match):
    """
    Sprawdza, czy gracz dostanie maksymalne 28 punktów:
    - 2:1 (zwycięzca 3 + gospodarze 2 + goście 2 + różnica 3 = 10 pkt)
    - Dokładny wynik (+5 pkt)
    - Pierwsza drużyna: HOME (+2 pkt)
    - Strzelec: Lewandowski (+3 pkt)
    - Bonus z kursu: 4.20 na Polskę (+3 pkt)
    - Perfekcyjny mecz (+5 pkt)
    Razem: 10 + 5 + 2 + 3 + 3 + 5 = 28 pkt
    """
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match,
        predicted_home=2, predicted_away=1,
        predicted_first_team='HOME',
        predicted_scorer='Lewandowski'
    )
    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()
    assert prediction.points == 28

@pytest.mark.django_db
def test_correct_winner_and_scorer_no_bonus(test_user, finished_match):
    """
    Gracz trafia:
    - Wynik 3:0 (zwycięzca 3 pkt, reszta źle) = 3 pkt
    - Pierwsza drużyna: AWAY (źle = 0 pkt)
    - Strzelec: müller (dobrze, wielkość liter nie ma znaczenia = +3 pkt)
    - Kurs na wygraną: 4.20 (+3 pkt)
    Razem: 3 + 0 + 3 + 3 = 9 pkt
    """
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match,
        predicted_home=3, predicted_away=0,
        predicted_first_team='AWAY',
        predicted_scorer='müller'
    )
    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()
    assert prediction.points == 9

@pytest.mark.django_db
def test_wrong_winner_but_correct_scorer(test_user, finished_match):
    """
    Gracz trafia tylko wygraną Niemiec (0 punktów za mecz),
    ale zgaduje, że Müller strzeli gola. Nie ma bonusu za kurs bo nie zgadł wyniku.
    Razem: 3 pkt za strzelca.
    """
    prediction = Prediction.objects.create(
        user=test_user, match=finished_match,
        predicted_home=0, predicted_away=2,
        predicted_scorer='Müller'
    )
    ScoringService.calculate_points_for_match(finished_match)
    prediction.refresh_from_db()
    assert prediction.points == 3