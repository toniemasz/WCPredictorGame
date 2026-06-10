from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from tournament.models import ApiSyncStatus, Match
from tournament.services.import_service import ImportService


class MatchAutoUpdateService:
    LIVE_REFRESH_INTERVAL = timedelta(minutes=5)
    KICKOFF_REFRESH_INTERVAL = timedelta(minutes=5)
    LOCK_KEY = "match-auto-update-lock"
    LOCK_TIMEOUT_SECONDS = 120

    @classmethod
    def check_and_update_matches(cls, now=None):
        now = now or timezone.now()

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

        if not cls._acquire_lock():
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

        if cls._has_finished_match_without_final_update():
            return cls._build_decision(
                should_update=True,
                reason="finished_needs_final_sync",
                message="Znaleziono zakończony mecz bez finalnej aktualizacji.",
            )

        last_success_at = cls._get_last_success_at()
        if cls._has_live_match() and cls._is_stale(
            last_success_at,
            now,
            cls.LIVE_REFRESH_INTERVAL,
        ):
            return cls._build_decision(
                should_update=True,
                reason="live_refresh_due",
                message="Trwa mecz, a ostatnia aktualizacja jest starsza niż 5 minut.",
            )

        if cls._has_started_scheduled_match(now) and cls._is_stale(
            last_success_at,
            now,
            cls.KICKOFF_REFRESH_INTERVAL,
        ):
            return cls._build_decision(
                should_update=True,
                reason="kickoff_passed",
                message="Najbliższy zaplanowany mecz powinien już się rozpocząć.",
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
    def _get_last_success_at(cls):
        sync_status = cls._get_sync_status()
        if not sync_status:
            return None
        return sync_status.last_success_at

    @staticmethod
    def _get_sync_status():
        return ApiSyncStatus.objects.filter(
            sync_name=ApiSyncStatus.SYNC_MATCHES,
        ).first()

    @staticmethod
    def _is_stale(last_success_at, now, interval):
        return not last_success_at or last_success_at <= now - interval

    @classmethod
    def _acquire_lock(cls):
        return cache.add(
            cls.LOCK_KEY,
            timezone.now().isoformat(),
            timeout=cls.LOCK_TIMEOUT_SECONDS,
        )

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
