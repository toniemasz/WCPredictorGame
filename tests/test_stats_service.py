import pytest
from django.urls import reverse
from django.utils import timezone

from tournament.models import Prediction
from tournament.services.scoring_service import ScoringService
from tournament.services.stats_service import StatsService


def _breakdown(*keys, bonus_points=0):
    data = {
        key: {"name": key, "points": 1}
        for key in keys
    }
    if bonus_points:
        data["bonus"] = {"name": "Bonus x2", "points": bonus_points}
    return data


def _finished_match(make_match, stage="Runda 1", home_score=2, away_score=1, **overrides):
    defaults = {
        "stage": stage,
        "status": "FINISHED",
        "home_score": home_score,
        "away_score": away_score,
        "kickoff": timezone.now(),
    }
    defaults.update(overrides)
    return make_match(**defaults)


def _prediction(user, match, points=0, breakdown=None, **overrides):
    defaults = {
        "user": user,
        "match": match,
        "predicted_home": match.home_score or 0,
        "predicted_away": match.away_score or 0,
        "points": points,
        "points_breakdown": breakdown if breakdown is not None else {},
    }
    defaults.update(overrides)
    return Prediction.objects.create(**defaults)


@pytest.mark.django_db
def test_stage_is_finished_only_when_all_matches_finished_with_scores(make_match):
    _finished_match(make_match, stage="Runda 1", home_score=1, away_score=0)
    _finished_match(make_match, stage="Runda 1", home_score=0, away_score=0)

    assert StatsService.is_stage_finished("Runda 1") is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status,home_score,away_score",
    [
        ("SCHEDULED", None, None),
        ("FINISHED", None, 1),
        ("FINISHED", 1, None),
    ],
)
def test_stage_is_not_finished_if_one_match_is_scheduled_or_missing_score(make_match, status, home_score, away_score):
    _finished_match(make_match, stage="Runda 1", home_score=1, away_score=0)
    make_match(stage="Runda 1", status=status, home_score=home_score, away_score=away_score)

    assert StatsService.is_stage_finished("Runda 1") is False


@pytest.mark.django_db
def test_user_stats_counts_predicted_matches(user, make_match):
    matches = [_finished_match(make_match, stage="Runda 1") for _ in range(3)]
    _prediction(user, matches[0], points=2, breakdown=_breakdown("home_or_away_winner"))
    _prediction(user, matches[1], points=5, breakdown=_breakdown("exact_score"))

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["predicted_matches"] == 2
    assert stats["missing_matches"] == 1
    assert stats["prediction_percent"] == 66.7


@pytest.mark.django_db
def test_user_stats_counts_exact_scores(user, make_match):
    first = _finished_match(make_match, stage="Runda 1")
    second = _finished_match(make_match, stage="Runda 1", home_score=1, away_score=1)
    _prediction(user, first, points=5, breakdown=_breakdown("exact_score"))
    _prediction(user, second, points=2, breakdown=_breakdown("home_or_away_winner"))

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["exact_scores"] == 1
    assert stats["exact_percent"] == 50.0


@pytest.mark.django_db
def test_user_stats_counts_correct_outcomes(user, make_match):
    home_win = _finished_match(make_match, stage="Runda 1", home_score=2, away_score=0)
    draw = _finished_match(make_match, stage="Runda 1", home_score=1, away_score=1)
    _prediction(user, home_win, points=2, breakdown=_breakdown("home_or_away_winner"))
    _prediction(user, draw, points=0, breakdown={})

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["correct_outcomes"] == 1
    assert stats["outcome_percent"] == 50.0


@pytest.mark.django_db
def test_user_stats_counts_percentages(user, make_match):
    matches = [_finished_match(make_match, stage="Runda 1") for _ in range(4)]
    _prediction(user, matches[0], points=5, breakdown=_breakdown("exact_score", "home_or_away_winner"))
    _prediction(user, matches[1], points=2, breakdown=_breakdown("home_or_away_winner"))

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["prediction_percent"] == 50.0
    assert stats["exact_percent"] == 50.0
    assert stats["outcome_percent"] == 100.0


@pytest.mark.django_db
def test_user_stats_handles_no_predictions(user, make_match):
    _finished_match(make_match, stage="Runda 1")

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["predicted_matches"] == 0
    assert stats["total_points"] == 0
    assert stats["average_points"] == 0.0
    assert stats["message"]


@pytest.mark.django_db
def test_global_stats_counts_round_participants(user, other_user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(user, match, points=4, breakdown=_breakdown("home_or_away_winner"))
    _prediction(other_user, match, points=1, breakdown={})

    stats = StatsService.get_global_stats("Runda 1")

    assert stats["participant_count"] == 2
    assert stats["prediction_count"] == 2


@pytest.mark.django_db
def test_global_stats_counts_average_points_per_user(user, other_user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(user, match, points=6, breakdown=_breakdown("exact_score"))
    _prediction(other_user, match, points=2, breakdown=_breakdown("home_or_away_winner"))

    stats = StatsService.get_global_stats("Runda 1")

    assert stats["average_points_per_user"] == 4.0
    assert stats["average_points_per_prediction"] == 4.0


@pytest.mark.django_db
def test_round_ranking_sorts_users_by_points(user, other_user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(user, match, points=2, breakdown=_breakdown("home_or_away_winner"))
    _prediction(other_user, match, points=9, breakdown=_breakdown("exact_score"))

    ranking = StatsService.get_round_ranking("Runda 1")

    assert [row["user"] for row in ranking] == [other_user, user]
    assert [row["rank"] for row in ranking] == [1, 2]


@pytest.mark.django_db
def test_bonus_x2_is_included_in_user_and_global_stats(user, other_user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(
        user,
        match,
        points=10,
        breakdown=_breakdown("exact_score", bonus_points=5),
        is_doubled=True,
    )
    _prediction(other_user, match, points=2, breakdown=_breakdown("home_or_away_winner"))

    user_stats = StatsService.get_user_stats(user, "Runda 1")
    global_stats = StatsService.get_global_stats("Runda 1")

    assert user_stats["bonus_used"] == 1
    assert user_stats["bonus_points"] == 5
    assert global_stats["bonus_used"] == 1
    assert global_stats["bonus_points"] == 5


@pytest.mark.django_db
def test_stats_view_works_for_logged_user(client, user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(user, match, points=5, breakdown=_breakdown("exact_score"))
    client.force_login(user)

    response = client.get(reverse("stats"))

    assert response.status_code == 200
    assert "Moje statystyki" in response.content.decode()


@pytest.mark.django_db
def test_home_page_shows_summary_only_when_finished_round_exists(client, user, make_match):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(user, match, points=5, breakdown=_breakdown("exact_score"))
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Podsumowanie rundy" in response.content.decode()


@pytest.mark.django_db
def test_home_page_without_finished_round_does_not_error(client, user, future_match):
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Podsumowanie rundy" not in response.content.decode()


@pytest.mark.django_db
def test_stats_service_delegates_scoring_when_prediction_breakdown_is_missing(user, make_match, monkeypatch):
    match = _finished_match(make_match, stage="Runda 1")
    _prediction(
        user,
        match,
        predicted_home=1,
        predicted_away=0,
        points=0,
        points_breakdown=None,
    )
    calls = []

    def fake_calculate(match_arg, prediction_arg):
        calls.append((match_arg.id, prediction_arg.id))
        return 7, {"home_or_away_winner": {"name": "outcome", "points": 2}}

    monkeypatch.setattr(ScoringService, "calculate_points", staticmethod(fake_calculate))

    stats = StatsService.get_user_stats(user, "Runda 1")

    assert stats["total_points"] == 7
    assert calls
