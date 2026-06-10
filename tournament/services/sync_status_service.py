from django.utils import timezone

from tournament.models import ApiSyncStatus


class SyncStatusService:
    @staticmethod
    def record_attempt(sync_name):
        status, _ = ApiSyncStatus.objects.get_or_create(sync_name=sync_name)
        status.status = ApiSyncStatus.STATUS_PENDING
        status.last_attempt_at = timezone.now()
        status.save(update_fields=["status", "last_attempt_at"])
        return status

    @staticmethod
    def record_success(sync_name, processed_count=0, created_count=0):
        status, _ = ApiSyncStatus.objects.get_or_create(sync_name=sync_name)
        status.status = ApiSyncStatus.STATUS_SUCCESS
        status.last_attempt_at = timezone.now()
        status.last_success_at = status.last_attempt_at
        status.last_error = ""
        status.processed_count = processed_count
        status.created_count = created_count
        status.save(update_fields=[
            "status",
            "last_attempt_at",
            "last_success_at",
            "last_error",
            "processed_count",
            "created_count",
        ])
        return status

    @staticmethod
    def record_error(sync_name, error_message):
        status, _ = ApiSyncStatus.objects.get_or_create(sync_name=sync_name)
        status.status = ApiSyncStatus.STATUS_ERROR
        status.last_attempt_at = timezone.now()
        status.last_error = str(error_message)[:1000]
        status.save(update_fields=[
            "status",
            "last_attempt_at",
            "last_error",
        ])
        return status

    @staticmethod
    def get_matches_sync_info():
        status = ApiSyncStatus.objects.filter(
            sync_name=ApiSyncStatus.SYNC_MATCHES
        ).first()

        if not status:
            return {
                "status": "unknown",
                "status_label": "Brak danych",
                "last_success_at": None,
                "last_attempt_at": None,
                "processed_count": 0,
                "created_count": 0,
                "last_error": "",
            }

        return {
            "status": status.status,
            "status_label": status.get_status_display(),
            "last_success_at": status.last_success_at,
            "last_attempt_at": status.last_attempt_at,
            "processed_count": status.processed_count,
            "created_count": status.created_count,
            "last_error": status.last_error,
        }
