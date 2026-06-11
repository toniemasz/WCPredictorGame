import pytest
from django.urls import reverse

from tournament.models import Prediction
from tournament.services.achievement_service import AchievementService
from tournament.services.profile_service import ProfileService


def _achievement_by_slug(achievements, slug):
    return next(achievement for achievement in achievements if achievement["slug"] == slug)


@pytest.mark.django_db
def test_achievement_service_unlocks_perfect_pick_and_related_achievements(user, finished_match):
    Prediction.objects.create(
        user=user,
        match=finished_match,
        predicted_home=2,
        predicted_away=1,
        predicted_first_team="HOME",
        predicted_scorer="Lewandowski",
        points=30,
        is_doubled=True,
        points_breakdown={
            "exact_score": {"points": 5},
            "diff_correct_outcome": {"points": 2},
            "home_correct_outcome": {"points": 3},
            "away_correct_outcome": {"points": 3},
            "home_or_away_winner": {"points": 2},
            "first_team": {"points": 5},
            "first_scorer": {"points": 10},
            "bonus": {"points": 15},
        },
    )

    achievements = AchievementService.get_user_achievements(user)

    assert _achievement_by_slug(achievements, "perfect_pick")["unlocked"] is True
    assert _achievement_by_slug(achievements, "good_scorer")["unlocked"] is True
    assert _achievement_by_slug(achievements, "bonus_profit")["unlocked"] is True


@pytest.mark.django_db
def test_achievement_service_keeps_locked_achievements_when_requirements_are_missing(user, finished_match):
    Prediction.objects.create(
        user=user,
        match=finished_match,
        predicted_home=0,
        predicted_away=0,
        points=0,
        points_breakdown={},
    )

    achievements = AchievementService.get_user_achievements(user)

    assert _achievement_by_slug(achievements, "zero_points")["unlocked"] is True
    assert _achievement_by_slug(achievements, "perfect_pick")["unlocked"] is False
    assert _achievement_by_slug(achievements, "ten_predictions")["unlocked"] is False


@pytest.mark.django_db
def test_achievement_service_unlocks_prediction_count_achievements(user, make_match):
    matches = [
        make_match(stage=f"Runda {index}")
        for index in range(10)
    ]
    for index, match in enumerate(matches):
        Prediction.objects.create(
            user=user,
            match=match,
            predicted_home=index % 3,
            predicted_away=0,
        )

    summary = AchievementService.get_user_summary(user)

    assert _achievement_by_slug(summary["achievements"], "ten_predictions")["unlocked"] is True
    assert summary["unlocked_count"] >= 1


@pytest.mark.django_db
def test_achievement_service_unlocks_all_matches_when_user_predicted_every_match(user, make_match):
    matches = [make_match(stage=f"Runda {index}") for index in range(3)]
    for match in matches:
        Prediction.objects.create(
            user=user,
            match=match,
            predicted_home=1,
            predicted_away=0,
        )

    achievements = AchievementService.get_user_achievements(user)

    assert _achievement_by_slug(achievements, "all_matches")["unlocked"] is True


@pytest.mark.django_db
def test_profile_context_includes_public_achievement_summary(user, other_user, finished_match):
    Prediction.objects.create(
        user=other_user,
        match=finished_match,
        predicted_home=2,
        predicted_away=1,
        points=5,
        points_breakdown={"exact_score": {"points": 5}},
    )

    context = ProfileService.get_profile_context(user, target_user=other_user)

    assert context["achievement_summary"]["total_count"] == len(AchievementService.ACHIEVEMENTS)
    assert _achievement_by_slug(
        context["achievement_summary"]["achievements"],
        "exact_score",
    )["unlocked"] is True


@pytest.mark.django_db
def test_achievements_view_works_for_logged_user(client, user):
    client.force_login(user)

    response = client.get(reverse("achievements"))

    assert response.status_code == 200
    assert "Twoje odznaki" in response.content.decode()
