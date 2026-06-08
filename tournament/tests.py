import math
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from tournament.models import Team, Match, Prediction
from tournament.services.scoring_service import (
    ScoringService,
    correct_result_points,
    correct_goal_diff_points,
    correct_home_or_away_goals_points,
    correct_home_or_away_win_points,
    correct_first_scorer_points,
    correct_first_team_scored,
)

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="tester",
        password="123"
    )


@pytest.fixture
def teams(db):
    home = Team.objects.create(name="Poland", code="POL")
    away = Team.objects.create(name="Germany", code="GER")
    return home, away


@pytest.fixture
def match(db, teams):
    home, away = teams

    return Match.objects.create(
        home_team=home,
        away_team=away,
        kickoff=timezone.now(),
        status="FINISHED",

        home_score=2,
        away_score=1,

        home_odds=Decimal("4.20"),
        draw_odds=Decimal("3.50"),
        away_odds=Decimal("1.70"),

        first_scoring_team="HOME",
        first_scorer="Lewandowski"
    )

@pytest.mark.django_db
def test_exact_score(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=1
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "exact_score" in breakdown
    assert breakdown["exact_score"]["points"] == correct_result_points

@pytest.mark.django_db
def test_goal_difference(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=3,
        predicted_away=2
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "diff_correct_outcome" in breakdown
    assert breakdown["diff_correct_outcome"]["points"] == correct_goal_diff_points
    assert points == (
            correct_goal_diff_points +
            correct_home_or_away_win_points +
            round(math.log(float(match.home_odds) / 3) * 10)
    )

@pytest.mark.django_db
def test_correct_home_goals(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=5
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "home_correct_outcome" in breakdown
    assert breakdown["home_correct_outcome"]["points"] == correct_home_or_away_goals_points

@pytest.mark.django_db
def test_correct_away_goals(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=7,
        predicted_away=1
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "away_correct_outcome" in breakdown
    assert breakdown["away_correct_outcome"]["points"] == correct_home_or_away_goals_points

@pytest.mark.django_db
def test_correct_winner(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=8,
        predicted_away=0
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "home_or_away_winner" in breakdown
    assert breakdown["home_or_away_winner"]["points"] == correct_home_or_away_win_points

@pytest.mark.django_db
def test_first_scoring_team(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
        predicted_first_team="HOME"
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "first_team" in breakdown
    assert breakdown["first_team"]["points"] == correct_first_team_scored

@pytest.mark.django_db
def test_first_scorer(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
        predicted_scorer="lewandowski"
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "first_scorer" in breakdown
    assert breakdown["first_scorer"]["points"] == correct_first_scorer_points

@pytest.mark.django_db
def test_underdog_bonus(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=5,
        predicted_away=0
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    expected_bonus = round(
        math.log(float(match.home_odds) / 3) * 10
    )

    assert "underdog_bonus_home" in breakdown
    assert breakdown["underdog_bonus_home"]["points"] == expected_bonus

@pytest.mark.django_db
def test_double_bonus(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=1,
        is_doubled=True
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "bonus" in breakdown

    base_points = breakdown["bonus"]["points"]

    assert points == base_points * 2

@pytest.mark.django_db
def test_no_points(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=4,
        predicted_first_team="AWAY",
        predicted_scorer="Klose"
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert points == 0
    assert breakdown == {}

@pytest.mark.django_db
def test_match_without_result(teams, user):

    home, away = teams

    match = Match.objects.create(
        home_team=home,
        away_team=away,
        kickoff=timezone.now()
    )

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=1
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert points == 0
    assert breakdown == {}

@pytest.mark.django_db
def test_exact_score(match, user):

    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=1
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert breakdown["exact_score"]["points"] == 5

    assert points == (
        correct_result_points +
        correct_goal_diff_points +
        correct_home_or_away_win_points +
        round(math.log(float(match.home_odds) / 3) * 10)
    )