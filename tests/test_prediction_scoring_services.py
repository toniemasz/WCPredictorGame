import math
from datetime import timezone as datetime_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.utils import timezone

from tournament.models import BonusUsage, Match, Prediction
from tournament.services.prediction_service import PredictionService
from tournament.services.scoring_service import (
    ScoringService,
    correct_first_scorer_points,
    correct_first_team_scored,
    correct_goal_diff_points,
    correct_home_or_away_goals_points,
    correct_home_or_away_win_points,
    correct_result_points,
)


@pytest.mark.django_db
def test_save_prediction_creates_prediction_without_bonus(user, future_match):
    result = PredictionService.save_prediction(
        user,
        future_match.id,
        {
            "predicted_home": "2",
            "predicted_away": "1",
            "predicted_first_team": "HOME",
            "predicted_scorer": "Lewandowski",
        },
    )

    prediction = Prediction.objects.get(user=user, match=future_match)
    assert prediction.predicted_home == 2
    assert prediction.predicted_away == 1
    assert prediction.predicted_first_team == "HOME"
    assert prediction.predicted_scorer == "Lewandowski"
    assert result["bonus_remaining"] == 2
    assert result["limit_reached"] is False


@pytest.mark.django_db
def test_save_prediction_rejects_started_match(user, make_match):
    match = make_match(kickoff=timezone.now(), status="LIVE")

    with pytest.raises(ValueError, match="Mecz już się rozpoczął"):
        PredictionService.save_prediction(
            user,
            match.id,
            {"predicted_home": "1", "predicted_away": "1"},
        )


@pytest.mark.django_db
@pytest.mark.parametrize("home,away", [(None, "1"), ("", "1"), ("1", None), ("1", "")])
def test_save_prediction_requires_both_scores(user, future_match, home, away):
    with pytest.raises(ValueError, match="Wpisz obie wartości"):
        PredictionService.save_prediction(
            user,
            future_match.id,
            {"predicted_home": home, "predicted_away": away},
        )


@pytest.mark.django_db
@pytest.mark.parametrize("home,away", [("-1", "0"), ("1.5", "0"), ("abc", "0")])
def test_save_prediction_rejects_invalid_score_values(user, future_match, home, away):
    with pytest.raises(ValueError):
        PredictionService.save_prediction(
            user,
            future_match.id,
            {"predicted_home": home, "predicted_away": away},
        )


@pytest.mark.django_db
def test_save_prediction_uses_timezone_aware_kickoff_consistently(user, make_match):
    warsaw_tz = ZoneInfo("Europe/Warsaw")
    kickoff = timezone.datetime(2026, 6, 11, 21, 0, tzinfo=warsaw_tz)
    match = make_match(kickoff=kickoff)

    with pytest.raises(ValueError, match="Mecz już się rozpoczął"):
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                timezone,
                "now",
                lambda: timezone.datetime(2026, 6, 11, 19, 1, tzinfo=datetime_timezone.utc),
            )
            PredictionService.save_prediction(
                user,
                match.id,
                {"predicted_home": "1", "predicted_away": "0"},
            )


@pytest.mark.django_db
@override_settings(BONUS_LIMIT_PER_STAGE=1)
def test_save_prediction_enforces_bonus_limit(user, make_match):
    first_match = make_match(stage="Runda bonus")
    second_match = make_match(stage="Runda bonus")

    first_result = PredictionService.save_prediction(
        user,
        first_match.id,
        {"predicted_home": "1", "predicted_away": "0", "is_doubled": True},
    )

    assert first_result["bonus_remaining"] == 0
    assert first_result["limit_reached"] is True

    with pytest.raises(ValueError, match="Wykorzystałeś limit bonusów"):
        PredictionService.save_prediction(
            user,
            second_match.id,
            {"predicted_home": "2", "predicted_away": "0", "is_doubled": True},
        )


@pytest.mark.django_db
def test_save_prediction_removes_existing_bonus(user, future_match):
    Prediction.objects.create(
        user=user,
        match=future_match,
        predicted_home=1,
        predicted_away=0,
        is_doubled=True,
    )
    BonusUsage.objects.create(user=user, stage=future_match.stage, count=1)

    result = PredictionService.save_prediction(
        user,
        future_match.id,
        {"predicted_home": "1", "predicted_away": "1", "is_doubled": False},
    )

    prediction = Prediction.objects.get(user=user, match=future_match)
    bonus_usage = BonusUsage.objects.get(user=user, stage=future_match.stage)
    assert prediction.is_doubled is False
    assert bonus_usage.count == 0
    assert result["bonus_remaining"] == 2


@pytest.mark.django_db
def test_save_prediction_allows_explicit_no_scorer_with_no_goals(user, future_match):
    PredictionService.save_prediction(
        user,
        future_match.id,
        {
            "predicted_home": "0",
            "predicted_away": "0",
            "predicted_first_team": "NONE",
            "predicted_scorer": ScoringService.NO_SCORER,
        },
    )

    prediction = Prediction.objects.get(user=user, match=future_match)
    assert prediction.predicted_first_team == "NONE"
    assert prediction.predicted_scorer == ScoringService.NO_SCORER


@pytest.mark.django_db
def test_save_prediction_allows_no_scorer_with_scoring_team(user, future_match):
    PredictionService.save_prediction(
        user,
        future_match.id,
        {
            "predicted_home": "1",
            "predicted_away": "0",
            "predicted_first_team": "HOME",
            "predicted_scorer": ScoringService.NO_SCORER,
        },
    )

    prediction = Prediction.objects.get(user=user, match=future_match)
    assert prediction.predicted_first_team == "HOME"
    assert prediction.predicted_scorer == ScoringService.NO_SCORER


@pytest.mark.django_db
def test_save_prediction_allows_scorer_with_no_goals(user, future_match):
    PredictionService.save_prediction(
        user,
        future_match.id,
        {
            "predicted_home": "0",
            "predicted_away": "0",
            "predicted_first_team": "NONE",
            "predicted_scorer": "Lewandowski",
        },
    )

    prediction = Prediction.objects.get(user=user, match=future_match)
    assert prediction.predicted_first_team == "NONE"
    assert prediction.predicted_scorer == "Lewandowski"


def test_get_rules_explanation_contains_point_values():
    rules = ScoringService.get_rules_explanation()

    assert f"+{correct_result_points}" in rules
    assert "Bonus x2" in rules


@pytest.mark.django_db
def test_calculate_points_exact_score_with_bonus(finished_match, user):
    prediction = Prediction.objects.create(
        user=user,
        match=finished_match,
        predicted_home=2,
        predicted_away=1,
        predicted_first_team="HOME",
        predicted_scorer=" lewandowski ",
        is_doubled=True,
    )

    points, breakdown = ScoringService.calculate_points(finished_match, prediction)
    expected_base = (
        correct_result_points
        + correct_goal_diff_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_win_points
        + correct_first_team_scored
        + correct_first_scorer_points
        + round(math.log(float(finished_match.home_odds) / 3) * 10)
    )

    assert points == expected_base * 2
    assert breakdown["bonus"]["points"] == expected_base


@pytest.mark.django_db
def test_calculate_points_draw_underdog(make_match, user):
    match = make_match(
        status="FINISHED",
        home_score=1,
        away_score=1,
        draw_odds=Decimal("4.00"),
    )
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "underdog_bonus_draw" in breakdown
    assert points == (
        correct_goal_diff_points
        + correct_home_or_away_win_points
        + round(math.log(float(match.draw_odds) / 3) * 10)
    )


@pytest.mark.django_db
def test_calculate_points_awards_outcome_points_for_correct_draw(make_match, user):
    match = make_match(
        status="FINISHED",
        home_score=2,
        away_score=2,
        draw_odds=Decimal("2.50"),
    )
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=1,
        predicted_away=1,
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert "home_or_away_winner" in breakdown
    assert points == correct_goal_diff_points + correct_home_or_away_win_points


@pytest.mark.django_db
def test_calculate_points_exact_zero_zero_gets_full_score_points(make_match, user):
    match = make_match(
        status="FINISHED",
        home_score=0,
        away_score=0,
        draw_odds=Decimal("2.50"),
        first_scoring_team="NONE",
        first_scorer="",
    )
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
        predicted_first_team="NONE",
        predicted_scorer="",
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert points == (
        correct_result_points
        + correct_goal_diff_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_win_points
        + correct_first_team_scored
    )
    assert set(breakdown) == {
        "exact_score",
        "diff_correct_outcome",
        "home_correct_outcome",
        "away_correct_outcome",
        "home_or_away_winner",
        "first_team",
    }


@pytest.mark.django_db
def test_calculate_points_explicit_no_scorer_gets_first_scorer_points(make_match, user):
    match = make_match(
        status="FINISHED",
        home_score=0,
        away_score=0,
        draw_odds=Decimal("2.50"),
        first_scoring_team="NONE",
        first_scorer=ScoringService.NO_SCORER,
    )
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
        predicted_first_team="NONE",
        predicted_scorer=ScoringService.NO_SCORER,
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert points == (
        correct_result_points
        + correct_goal_diff_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_goals_points
        + correct_home_or_away_win_points
        + correct_first_team_scored
        + correct_first_scorer_points
    )
    assert breakdown["first_scorer"]["points"] == correct_first_scorer_points


@pytest.mark.django_db
def test_calculate_points_goal_difference_uses_absolute_value(make_match, user):
    match = make_match(
        status="FINISHED",
        home_score=2,
        away_score=1,
    )
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=1,
        predicted_away=2,
    )

    points, breakdown = ScoringService.calculate_points(match, prediction)

    assert points == correct_goal_diff_points
    assert breakdown == {
        "diff_correct_outcome": {
            "name": "Poprawna różnica bramek",
            "points": correct_goal_diff_points,
        }
    }


@pytest.mark.django_db
def test_calculate_points_no_result_returns_zero(future_match, user):
    prediction = Prediction.objects.create(
        user=user,
        match=future_match,
        predicted_home=2,
        predicted_away=1,
    )

    assert ScoringService.calculate_points(future_match, prediction) == (0, {})


@pytest.mark.django_db
def test_recalculate_match_updates_prediction_points(make_match, user):
    match = make_match(status="FINISHED", home_score=None, away_score=None)
    prediction = Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=2,
        predicted_away=1,
    )
    Match.objects.filter(pk=match.pk).update(home_score=2, away_score=1)
    match.refresh_from_db()

    ScoringService.recalculate_match(match)
    prediction.refresh_from_db()

    assert prediction.points > 0
    assert "exact_score" in prediction.points_breakdown


@pytest.mark.django_db
def test_recalculate_finished_matches_only_recalculates_live_and_finished(make_match, monkeypatch):
    scheduled = make_match(status="SCHEDULED")
    live = make_match(status="LIVE")
    finished = make_match(status="FINISHED")
    called = []

    def fake_recalculate(cls, match):
        called.append(match.id)

    monkeypatch.setattr(ScoringService, "recalculate_match", classmethod(fake_recalculate))

    count = ScoringService.recalculate_finished_matches()

    assert count == 2
    assert set(called) == {live.id, finished.id}
    assert scheduled.id not in called
