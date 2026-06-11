from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from tournament.models import ApiSyncStatus, Match
from tournament.services.import_service import ImportService
from tournament.services.sync_status_service import SyncStatusService


class MatchAutoUpdateService:
    MIN_REFRESH_INTERVAL = timedelta(minutes=10)
    LIVE_REFRESH_INTERVAL = MIN_REFRESH_INTERVAL
    KICKOFF_REFRESH_INTERVAL = MIN_REFRESH_INTERVAL
    LOCK_KEY = "match-auto-update-lock"
    LOCK_TIMEOUT_SECONDS = 120

    @classmethod
    def check_and_update_matches(cls, now=None):
        now = now or timezone.now()

        if not cls.is_enabled():
            return cls._build_response(
                status="skipped",
                updated=False,
                reason="auto_sync_disabled",
                message="Automatyczna synchronizacja meczów jest wyłączona.",
                should_update=False,
            )

        running_response = cls._get_running_sync_response(now)
        if running_response:
            return running_response

        decision = cls._get_update_decision(now)
        if not decision["should_update"]:
            return cls._build_response(
                status="skipped",
                updated=False,
                reason=decision["reason"],
                message=decision["message"],
                should_update=False,
            )

        if not cls._acquire_lock(now):
            return cls._build_response(
                status="skipped",
                updated=False,
                reason="already_running",
                message="Aktualizacja wyników jest już w toku.",
                should_update=True,
            )

        try:
            ImportService.import_matches()
        except Exception as error:
            SyncStatusService.record_error(ApiSyncStatus.SYNC_MATCHES, error)
            return cls._build_response(
                status="error",
                updated=False,
                reason="api_error",
                message="Nie udało się zaktualizować wyników meczów.",
                should_update=True,
                error=str(error),
            )
        finally:
            cls._release_lock()

        return cls._build_response(
            status="updated",
            updated=True,
            reason=decision["reason"],
            message="Wyniki meczów zostały zaktualizowane.",
            should_update=True,
        )

    @staticmethod
    def is_enabled():
        return getattr(settings, "AUTO_MATCH_API_SYNC_ENABLED", True)

    @classmethod
    def _get_running_sync_response(cls, now):
        sync_status = cls._get_sync_status()
        if not sync_status:
            return None

        is_recent_pending = (
            sync_status.status == ApiSyncStatus.STATUS_PENDING
            and sync_status.last_attempt_at
            and sync_status.last_attempt_at >= now - timedelta(seconds=cls.LOCK_TIMEOUT_SECONDS)
        )
        if not is_recent_pending:
            return None

        return cls._build_response(
            status="skipped",
            updated=False,
            reason="already_running",
            message="Aktualizacja wyników jest już w toku.",
            should_update=True,
        )

    @classmethod
    def _get_update_decision(cls, now):
        if not Match.objects.exists():
            return cls._build_decision(
                should_update=False,
                reason="no_matches",
                message="Brak meczów do aktualizacji.",
            )

        last_attempt_at = cls._get_last_attempt_at()

        if cls._has_live_match() and cls._is_stale(
            last_attempt_at,
            now,
            cls.LIVE_REFRESH_INTERVAL,
        ):
            return cls._build_decision(
                should_update=True,
                reason="live_refresh_due",
                message="Trwa mecz, a ostatnia próba aktualizacji jest starsza niż 10 minut.",
            )

        if cls._has_started_scheduled_match(now) and cls._is_stale(
            last_attempt_at,
            now,
            cls.KICKOFF_REFRESH_INTERVAL,
        ):
            return cls._build_decision(
                should_update=True,
                reason="kickoff_passed",
                message="Najbliższy zaplanowany mecz powinien już się rozpocząć.",
            )

        if cls._has_finished_match_without_final_update() and cls._is_stale(
            last_attempt_at,
            now,
            cls.KICKOFF_REFRESH_INTERVAL,
        ):
            return cls._build_decision(
                should_update=True,
                reason="finished_needs_final_sync",
                message="Znaleziono zakończony mecz bez finalnej aktualizacji.",
            )

        return cls._build_decision(
            should_update=False,
            reason="fresh",
            message="Dane meczów są wystarczająco świeże.",
        )

    @staticmethod
    def _has_finished_match_without_final_update():
        return Match.objects.filter(
            status="FINISHED",
            final_api_update_at__isnull=True,
        ).exists()

    @staticmethod
    def _has_live_match():
        return Match.objects.filter(status="LIVE").exists()

    @staticmethod
    def _has_started_scheduled_match(now):
        next_scheduled_match = Match.objects.filter(
            status="SCHEDULED",
        ).order_by(
            "kickoff"
        ).values(
            "kickoff"
        ).first()

        return bool(
            next_scheduled_match
            and next_scheduled_match["kickoff"] <= now
        )

    @classmethod
    def _get_last_attempt_at(cls):
        sync_status = cls._get_sync_status()
        if not sync_status:
            return None
        return sync_status.last_attempt_at

    @staticmethod
    def _get_sync_status():
        return ApiSyncStatus.objects.filter(
            sync_name=ApiSyncStatus.SYNC_MATCHES,
        ).first()

    @staticmethod
    def _is_stale(last_attempt_at, now, interval):
        return not last_attempt_at or last_attempt_at <= now - interval

    @classmethod
    def _acquire_lock(cls, now):
        has_cache_lock = cache.add(
            cls.LOCK_KEY,
            timezone.now().isoformat(),
            timeout=cls.LOCK_TIMEOUT_SECONDS,
        )
        if not has_cache_lock:
            return False

        if cls._acquire_database_lock(now):
            return True

        cls._release_lock()
        return False

    @classmethod
    def _acquire_database_lock(cls, now):
        with transaction.atomic():
            status, _ = ApiSyncStatus.objects.select_for_update().get_or_create(
                sync_name=ApiSyncStatus.SYNC_MATCHES,
            )
            is_recent_pending = (
                status.status == ApiSyncStatus.STATUS_PENDING
                and status.last_attempt_at
                and status.last_attempt_at >= now - timedelta(seconds=cls.LOCK_TIMEOUT_SECONDS)
            )
            if is_recent_pending:
                return False

            status.status = ApiSyncStatus.STATUS_PENDING
            status.last_attempt_at = now
            status.save(update_fields=["status", "last_attempt_at"])
            return True

    @classmethod
    def _release_lock(cls):
        cache.delete(cls.LOCK_KEY)

    @staticmethod
    def _build_decision(should_update, reason, message):
        return {
            "should_update": should_update,
            "reason": reason,
            "message": message,
        }

    @staticmethod
    def _build_response(status, updated, reason, message, should_update, error=""):
        return {
            "status": status,
            "updated": updated,
            "should_update": should_update,
            "reason": reason,
            "message": message,
            "error": error,
        }
