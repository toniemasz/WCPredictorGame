from datetime import timedelta

import pytest
from django.core.cache import cache
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
def test_auto_update_imports_when_scheduled_match_kickoff_passed_and_sync_is_stale(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=1), status="SCHEDULED")
    _create_success_status(now - timedelta(minutes=6))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "kickoff_passed"
    assert calls == ["import"]


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
def test_auto_update_imports_live_match_every_five_minutes(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=20), status="LIVE", home_score=1, away_score=0)
    _create_success_status(now - timedelta(minutes=5))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "live_refresh_due"
    assert calls == ["import"]


@pytest.mark.django_db
def test_auto_update_skips_live_match_when_last_sync_is_younger_than_five_minutes(monkeypatch, make_match):
    now = timezone.now()
    make_match(kickoff=now - timedelta(minutes=20), status="LIVE", home_score=1, away_score=0)
    _create_success_status(now - timedelta(minutes=4, seconds=59))
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
    _create_success_status(now - timedelta(minutes=1))
    calls = _stub_import(monkeypatch)

    result = MatchAutoUpdateService.check_and_update_matches(now=now)

    assert result["status"] == "updated"
    assert result["reason"] == "finished_needs_final_sync"
    assert calls == ["import"]


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
