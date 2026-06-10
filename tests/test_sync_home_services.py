import pytest
from django.utils import timezone

from tournament.models import ApiSyncStatus
from tournament.services.home_service import HomePageService
from tournament.services.sync_status_service import SyncStatusService


@pytest.mark.django_db
def test_record_attempt_creates_pending_status():
    status = SyncStatusService.record_attempt(ApiSyncStatus.SYNC_MATCHES)

    assert status.status == ApiSyncStatus.STATUS_PENDING
    assert status.last_attempt_at is not None
    assert status.last_success_at is None


@pytest.mark.django_db
def test_record_success_updates_counts_and_clears_error():
    ApiSyncStatus.objects.create(
        sync_name=ApiSyncStatus.SYNC_MATCHES,
        status=ApiSyncStatus.STATUS_ERROR,
        last_error="old error",
    )

    status = SyncStatusService.record_success(
        ApiSyncStatus.SYNC_MATCHES,
        processed_count=8,
        created_count=3,
    )

    assert status.status == ApiSyncStatus.STATUS_SUCCESS
    assert status.last_attempt_at == status.last_success_at
    assert status.last_error == ""
    assert status.processed_count == 8
    assert status.created_count == 3


@pytest.mark.django_db
def test_record_error_truncates_error_message():
    status = SyncStatusService.record_error("custom", "x" * 1200)

    assert status.status == ApiSyncStatus.STATUS_ERROR
    assert status.last_attempt_at is not None
    assert len(status.last_error) == 1000


@pytest.mark.django_db
def test_get_matches_sync_info_returns_unknown_without_status():
    info = SyncStatusService.get_matches_sync_info()

    assert info["status"] == "unknown"
    assert info["status_label"] == "Brak danych"
    assert info["last_success_at"] is None


@pytest.mark.django_db
def test_get_matches_sync_info_returns_existing_status():
    now = timezone.now()
    ApiSyncStatus.objects.create(
        sync_name=ApiSyncStatus.SYNC_MATCHES,
        status=ApiSyncStatus.STATUS_SUCCESS,
        last_attempt_at=now,
        last_success_at=now,
        processed_count=4,
        created_count=2,
    )

    info = SyncStatusService.get_matches_sync_info()

    assert info["status"] == ApiSyncStatus.STATUS_SUCCESS
    assert info["status_label"] == "Zaktualizowano"
    assert info["processed_count"] == 4
    assert info["created_count"] == 2


@pytest.mark.django_db
def test_home_page_service_formats_dynamic_content(monkeypatch, settings):
    settings.BONUS_LIMIT_PER_STAGE = 7
    monkeypatch.setattr(
        SyncStatusService,
        "get_matches_sync_info",
        staticmethod(lambda: {"status": "ok"}),
    )

    context = HomePageService.get_context()

    assert context["matches_sync"] == {"status": "ok"}
    assert context["home_content"]["quick_steps"][1]["description"].startswith(
        "W każdej rundzie możesz wybrać do 7 meczów"
    )
    assert (
        "Dokładny wynik bramkowy: +5 punkty"
        in context["home_content"]["game_info"]["sections"][1]["items"]
    )
    assert (
        context["home_content"]["game_info"]["sections"][1]["items"]
        == HomePageService._get_scoring_rule_items()
    )
