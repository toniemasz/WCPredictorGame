from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from tournament.models import ApiSyncStatus
from tournament.services.import_service import ImportService
from tournament.services.match_auto_update_service import MatchAutoUpdateService


@pytest.fixture(autouse=True)
def clear_auto_update_cache():
    cache.delete(MatchAutoUpdateService.LOCK_KEY)
    yield
    cache.delete(MatchAutoUpdateService.LOCK_KEY)


def _create_success_status(last_success_at):
    return ApiSyncStatus.objects.create(
        sync_name=ApiSyncStatus.SYNC_MATCHES,
        status=ApiSyncStatus.STATUS_SUCCESS,
        last_attempt_at=last_success_at,
        last_success_at=last_success_at,
    )


def _create_error_status(last_attempt_at, last_success_at=None):
    return ApiSyncStatus.objects.create(
        sync_name=ApiSyncStatus.SYNC_MATCHES,
        status=ApiSyncStatus.STATUS_ERROR,
        last_attempt_at=last_attempt_at,
        last_success_at=last_success_at,
        last_error="api down",
    )


def _stub_import(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ImportService,
        "import_matches",
        staticmethod(lambda: calls.append("import")),
    )
    return calls


@pytest.mark.django_db
def test_auto_update_skips_when_database_has_no_matches(monkeypatch):
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_matches"
    assert result["updated"] is False
    assert calls == []


@pytest.mark.django_db
@override_settings(AUTO_MATCH_API_SYNC_ENABLED=False)
def test_auto_update_skips_when_auto_sync_is_disabled(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=2), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=30))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "auto_sync_disabled"
    assert result["should_update"] is False
    assert calls == []


@pytest.mark.django_db
def test_auto_update_skips_before_scheduled_match_kickoff_even_when_sync_is_stale(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now + timedelta(minutes=5), status="SCHEDULED")
    _create_success_status(now - timedelta(hours=1))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_imports_when_scheduled_match_kickoff_passed_and_sync_is_stale(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=2), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=11))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "kickoff_passed"
    assert calls == ["import"]


@pytest.mark.django_db
def test_auto_update_matches_user_entry_timing_example(monkeypatch, make_match):
    warsaw_tz = ZoneInfo("Europe/Warsaw")
    kickoff = timezone.datetime(2026, 6, 11, 21, 0, tzinfo=warsaw_tz)
    match = make_match(kickoff=kickoff, status="SCHEDULED")
    calls = _stub_import(monkeypatch)

    _create_success_status(timezone.datetime(2026, 6, 11, 20, 30, tzinfo=warsaw_tz))
    before_kickoff = MatchAutoUpdateService.check_and_update_matches(
        now=timezone.datetime(2026, 6, 11, 20, 55, tzinfo=warsaw_tz),
    )

    assert before_kickoff["status"] == "skipped"
    assert calls == []

    after_kickoff = MatchAutoUpdateService.check_and_update_matches(
        now=timezone.datetime(2026, 6, 11, 21, 2, tzinfo=warsaw_tz),
    )
    assert after_kickoff["status"] == "updated"
    assert after_kickoff["reason"] == "kickoff_passed"
    assert calls == ["import"]

    ApiSyncStatus.objects.filter(sync_name=ApiSyncStatus.SYNC_MATCHES).update(
        status=ApiSyncStatus.STATUS_SUCCESS,
        last_attempt_at=timezone.datetime(2026, 6, 11, 21, 2, tzinfo=warsaw_tz),
        last_success_at=timezone.datetime(2026, 6, 11, 21, 2, tzinfo=warsaw_tz),
    )
    match.status = "LIVE"
    match.save(update_fields=["status"])

    eight_minutes_after = MatchAutoUpdateService.check_and_update_matches(
        now=timezone.datetime(2026, 6, 11, 21, 8, tzinfo=warsaw_tz),
    )
    assert eight_minutes_after["status"] == "skipped"
    assert calls == ["import"]

    thirteen_minutes_after = MatchAutoUpdateService.check_and_update_matches(
        now=timezone.datetime(2026, 6, 11, 21, 13, tzinfo=warsaw_tz),
    )
    assert thirteen_minutes_after["status"] == "updated"
    assert thirteen_minutes_after["reason"] == "live_refresh_due"
    assert calls == ["import", "import"]


@pytest.mark.django_db
def test_auto_update_skips_when_scheduled_match_kickoff_passed_but_sync_is_fresh(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=1), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=2))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_imports_live_match_every_ten_minutes(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=20), status="LIVE", home_score=1, away_score=0)
    _create_success_status(now - timedelta(minutes=10))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "live_refresh_due"
    assert calls == ["import"]


@pytest.mark.django_db
def test_auto_update_skips_live_match_when_last_attempt_is_younger_than_ten_minutes(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=20), status="LIVE", home_score=1, away_score=0)
    _create_success_status(now - timedelta(minutes=9, seconds=59))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_skips_live_match_when_recent_failed_attempt_exists(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=20), status="LIVE", home_score=1, away_score=0)
    _create_error_status(
        last_attempt_at=now - timedelta(minutes=2),
        last_success_at=now - timedelta(hours=1),
    )
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_imports_finished_match_once_when_final_sync_is_missing(monkeypatch, make_match):
    now = timezone.now()
    make_match(
        kickoff=now - timedelta(hours=3),
        status="FINISHED",
        home_score=2,
        away_score=1,
        final_api_update_at=None,
    )
    _create_success_status(now - timedelta(minutes=11))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "finished_needs_final_sync"
    assert calls == ["import"]


@pytest.mark.django_db
def test_auto_update_skips_finished_final_sync_when_recent_attempt_exists(monkeypatch, make_match):
    now = timezone.now()
    make_match(
        kickoff=now - timedelta(hours=3),
        status="FINISHED",
        home_score=2,
        away_score=1,
        final_api_update_at=None,
    )
    _create_error_status(now - timedelta(minutes=2))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_skips_finished_match_after_final_sync(monkeypatch, make_match):
    now = timezone.now()
    make_match(
        kickoff=now - timedelta(hours=3),
        status="FINISHED",
        home_score=2,
        away_score=1,
        final_api_update_at=now - timedelta(hours=1),
    )
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_waits_for_next_match_after_finished_match_has_final_sync(monkeypatch, make_match):
    now = timezone.now()
    make_match(
        kickoff=now - timedelta(hours=2),
        status="FINISHED",
        home_score=2,
        away_score=1,
        final_api_update_at=now - timedelta(hours=1),
    )
    make_match(
        kickoff=now + timedelta(minutes=5),
        status="SCHEDULED",
        home_score=None,
        away_score=None,
    )
    _create_success_status(now - timedelta(hours=1))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "fresh"
    assert calls == []


@pytest.mark.django_db
def test_auto_update_repeats_process_for_next_match_after_its_kickoff(monkeypatch, make_match):
    now = timezone.now()
    make_match(
        kickoff=now - timedelta(hours=2),
        status="FINISHED",
        home_score=2,
        away_score=1,
        final_api_update_at=now - timedelta(hours=1),
    )
    make_match(
        kickoff=now - timedelta(minutes=2),
        status="SCHEDULED",
        home_score=None,
        away_score=None,
    )
    _create_success_status(now - timedelta(minutes=11))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "kickoff_passed"
    assert calls == ["import"]


@pytest.mark.django_db
def test_auto_update_skips_when_recent_pending_sync_exists(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=1), status="SCHEDULED")
    ApiSyncStatus.objects.create(
        sync_name=ApiSyncStatus.SYNC_MATCHES,
        status=ApiSyncStatus.STATUS_PENDING,
        last_attempt_at=now - timedelta(seconds=30),
    )
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "already_running"
    assert result["should_update"] is True
    assert calls == []


@pytest.mark.django_db
def test_auto_update_skips_when_cache_lock_exists(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=1), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=10))
    cache.add(MatchAutoUpdateService.LOCK_KEY, "locked", timeout=60)
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "already_running"
    assert result["should_update"] is True
    assert calls == []


@pytest.mark.django_db
def test_auto_update_returns_error_when_import_fails(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=1), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=10))

    def _raise_error():
        raise RuntimeError("api down")

    monkeypatch.setattr(ImportService, "import_matches", staticmethod(_raise_error))

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "error"
    assert result["reason"] == "api_error"
    assert result["updated"] is False
    assert result["error"] == "api down"
    assert cache.get(MatchAutoUpdateService.LOCK_KEY) is None


@pytest.mark.django_db
def test_auto_update_matches_view_returns_service_response(monkeypatch, client, user):
    client.force_login(user)
    monkeypatch.setattr(
        MatchAutoUpdateService,
        "check_and_update_matches",
        classmethod(lambda cls: {
            "status": "skipped",
            "updated": False,
            "should_update": False,
            "reason": "fresh",
            "message": "OK",
            "error": "",
        }),
    )

    response = client.get(reverse("auto_update_matches"))

    assert response.status_code == 200
    assert response.json()["reason"] == "fresh"
