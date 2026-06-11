from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone

from tournament.models import BonusUsage, Prediction, Profile, TeamPlayer
from tournament.services.import_service import ImportService
from tournament.services.match_service import MatchListService
from tournament.services.profile_service import ProfileService
from tournament.services.scoring_service import ScoringService


def _prepare_avatar_dirs(tmp_path, settings):
    static_root = tmp_path / "static"
    static_avatars = static_root / "avatars"
    static_avatars.mkdir(parents=True)
    (static_avatars / "default.png").write_bytes(b"default")
    (static_avatars / "static.webp").write_bytes(b"static")
    (static_avatars / "ignored.txt").write_text("ignored")

    media_root = tmp_path / "media"
    media_avatars = media_root / "avatars"
    media_avatars.mkdir(parents=True)
    (media_avatars / "media.png").write_bytes(b"media")

    settings.STATICFILES_DIRS = [static_root]
    settings.MEDIA_ROOT = media_root
    return static_root, media_root


@pytest.mark.django_db
def test_get_target_user_returns_current_or_requested_user(user, other_user):
    assert ProfileService.get_target_user(user) == user
    assert ProfileService.get_target_user(user, other_user.id) == other_user

    with pytest.raises(Http404):
        ProfileService.get_target_user(user, 999999)


@pytest.mark.django_db
def test_get_profile_context_for_owner_includes_avatars_and_matches(tmp_path, settings, user, future_match):
    _prepare_avatar_dirs(tmp_path, settings)
    Prediction.objects.create(
        user=user,
        match=future_match,
        predicted_home=1,
        predicted_away=0,
    )

    context = ProfileService.get_profile_context(user)

    assert context["target_user"] == user
    assert context["profile_avatar_url"] == "/static/avatars/default.png"
    assert {option["value"] for option in context["available_avatars"]} == {
        "default.png",
        "static.webp",
        "avatars/media.png",
    }
    assert context["matches_by_stage"]["Runda 1"][0].target_prediction is not None


@pytest.mark.django_db
def test_get_profile_context_for_other_user_hides_avatar_options(tmp_path, settings, user, other_user):
    _prepare_avatar_dirs(tmp_path, settings)

    context = ProfileService.get_profile_context(user, target_user=other_user)

    assert context["target_user"] == other_user
    assert context["available_avatars"] == []


@pytest.mark.django_db
def test_get_user_matches_by_stage_maps_target_predictions(user, make_match):
    first = make_match(stage="Runda 1")
    second = make_match(stage="Runda 2")
    Prediction.objects.create(
        user=user,
        match=second,
        predicted_home=2,
        predicted_away=1,
    )

    matches_by_stage = ProfileService.get_user_matches_by_stage(user)

    assert matches_by_stage["Runda 1"][0].id == first.id
    assert matches_by_stage["Runda 1"][0].target_prediction is None
    assert matches_by_stage["Runda 2"][0].target_prediction.predicted_home == 2


@pytest.mark.django_db
def test_get_available_avatar_options_marks_selected_by_filename(tmp_path, settings):
    _prepare_avatar_dirs(tmp_path, settings)

    options = ProfileService.get_available_avatar_options("avatars/media.png")
    selected = [option for option in options if option["selected"]]

    assert len(selected) == 1
    assert selected[0]["value"] == "avatars/media.png"


@pytest.mark.django_db
def test_update_profile_changes_username_and_avatar(tmp_path, settings, user):
    _prepare_avatar_dirs(tmp_path, settings)

    changed = ProfileService.update_profile(
        user,
        user,
        {"username": "new-name", "avatar": "avatars/media.png"},
    )

    user.refresh_from_db()
    user.profile.refresh_from_db()
    assert changed is True
    assert user.username == "new-name"
    assert user.profile.avatar == "avatars/media.png"


@pytest.mark.django_db
def test_update_profile_ignores_non_owner_and_invalid_avatar(tmp_path, settings, user, other_user):
    _prepare_avatar_dirs(tmp_path, settings)

    assert ProfileService.update_profile(user, other_user, {"avatar": "static.webp"}) is False

    changed = ProfileService.update_profile(user, user, {"avatar": "missing.png"})
    user.profile.refresh_from_db()
    assert changed is False
    assert user.profile.avatar == "default.png"


@pytest.mark.django_db
def test_update_profile_duplicate_username_raises_value_error(user, other_user):
    with pytest.raises(ValueError, match="nazwa użytkownika"):
        ProfileService.update_profile(user, user, {"username": other_user.username})


@pytest.mark.django_db
def test_get_leaderboard_profiles_orders_by_points(user, other_user, make_match):
    match = make_match(status="FINISHED", home_score=1, away_score=0)
    Prediction.objects.create(user=user, match=match, predicted_home=1, predicted_away=0, points=4)
    Prediction.objects.create(user=other_user, match=match, predicted_home=0, predicted_away=0, points=9)

    profiles = ProfileService.get_leaderboard_profiles()

    assert [profile.user for profile in profiles[:2]] == [other_user, user]
    assert profiles[0].total_points == 9
    assert profiles[0].avatar_url


@pytest.mark.django_db
def test_get_avatar_url_handles_media_static_absolute_and_fallback(tmp_path, settings):
    _prepare_avatar_dirs(tmp_path, settings)

    assert ProfileService.get_avatar_url("https://example.com/a.png") == "https://example.com/a.png"
    assert ProfileService.get_avatar_url("/custom/a.png") == "/custom/a.png"
    assert ProfileService.get_avatar_url("avatars/media.png") == "/media/avatars/media.png"
    assert ProfileService.get_avatar_url("static.webp") == "/static/avatars/static.webp"
    assert ProfileService.get_avatar_url("missing.png") == "/static/avatars/default.png"
    assert ProfileService.get_default_avatar_url() == "/static/avatars/default.png"
    assert ProfileService.get_static_avatar_dir().name == "avatars"
    assert ProfileService.get_media_avatar_dir().name == "avatars"


@pytest.mark.django_db
def test_match_list_context_empty_database_triggers_import(monkeypatch, user):
    called = []
    monkeypatch.setattr(ImportService, "import_matches", staticmethod(lambda: called.append(True)))

    context = MatchListService.get_match_list_context(user)

    assert called == [True]
    assert context["summary"]["total_matches"] == 0
    assert context["stage_groups"] == []


@pytest.mark.django_db
def test_match_list_context_builds_stage_summary(user, other_user, make_match, teams):
    home, _ = teams
    TeamPlayer.objects.create(api_player_id=1, team=home, name="Player")
    scheduled = make_match(stage="Runda 1")
    live = make_match(stage="Runda 2", status="LIVE", kickoff=timezone.now() - timedelta(minutes=5))
    Prediction.objects.create(
        user=user,
        match=scheduled,
        predicted_home=1,
        predicted_away=0,
        predicted_first_team="HOME",
    )
    Prediction.objects.create(user=other_user, match=live, predicted_home=2, predicted_away=2)
    BonusUsage.objects.create(user=user, stage="Runda 1", count=1)

    context = MatchListService.get_match_list_context(user)
    stages_by_name = {
        stage["name"]: stage
        for stage in context["stage_groups"]
    }
    scheduled_stage = stages_by_name["Runda 1"]
    live_stage = stages_by_name["Runda 2"]
    first_match = scheduled_stage["matches"][0]
    live_match = live_stage["matches"][0]

    assert context["summary"]["total_matches"] == 2
    assert context["summary"]["predicted_matches"] == 1
    assert context["summary"]["incomplete_predictions"] == 1
    assert scheduled_stage["predicted_matches"] == 1
    assert live_stage["status_label"] == "LIVE"
    assert first_match.bonus_remaining == 1
    assert first_match.has_incomplete_prediction is True
    assert first_match.available_players[0].name == "Player"
    assert live_match.can_view_public_predictions is True
    assert live_match.public_predictions_count == 1


@pytest.mark.django_db
def test_public_predictions_context_blocks_scheduled_match(future_match):
    with pytest.raises(ValueError, match="po rozpoczęciu"):
        MatchListService.get_public_predictions_context(future_match.id)


@pytest.mark.django_db
def test_public_predictions_context_returns_sorted_predictions(tmp_path, settings, user, other_user, make_match):
    _prepare_avatar_dirs(tmp_path, settings)
    match = make_match(status="LIVE", home_score=0, away_score=0)
    user.profile.avatar = "static.webp"
    user.profile.save(update_fields=["avatar"])
    Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=1,
        predicted_away=0,
        predicted_first_team="HOME",
        predicted_scorer="",
        points=2,
    )
    Prediction.objects.create(
        user=other_user,
        match=match,
        predicted_home=2,
        predicted_away=0,
        predicted_first_team="AWAY",
        predicted_scorer="Klose",
        points=5,
    )

    context = MatchListService.get_public_predictions_context(match.id)

    assert context["total_predictions"] == 2
    assert context["predictions"][0].user == other_user
    assert context["predictions"][0].first_team_label == "Niemcy"
    assert context["predictions"][1].avatar_url == "/static/avatars/static.webp"
    assert context["predictions"][1].missing_options == ["pierwszy strzelec"]


@pytest.mark.django_db
def test_public_predictions_context_labels_explicit_no_scorer(user, make_match):
    match = make_match(status="LIVE", home_score=0, away_score=0)
    Prediction.objects.create(
        user=user,
        match=match,
        predicted_home=0,
        predicted_away=0,
        predicted_first_team="NONE",
        predicted_scorer=ScoringService.NO_SCORER,
    )

    context = MatchListService.get_public_predictions_context(match.id)

    prediction = context["predictions"][0]
    assert prediction.predicted_scorer_label == ScoringService.NO_SCORER_LABEL
    assert prediction.missing_options == []


@pytest.mark.django_db
def test_public_predictions_context_returns_empty_list_for_live_match_without_predictions(make_match):
    match = make_match(status="LIVE", home_score=0, away_score=0)

    context = MatchListService.get_public_predictions_context(match.id)

    assert context["match"] == match
    assert context["predictions"] == []
    assert context["total_predictions"] == 0
