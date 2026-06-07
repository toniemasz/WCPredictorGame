from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from tournament.services.import_service import ImportService
from tournament.services.odds_sync import OddsSync
from tournament.models import Match

@shared_task
def daily_update():
    # To zostawiamy - np. na ściągnięcie planu meczów z samego rana
    ImportService.import_matches()
    OddsSync.connect_existing_matches()
    OddsSync.sync_odds()

@shared_task
def conditional_live_update():
    now = timezone.now()

    time_threshold = now + timedelta(minutes=15)

    has_live = Match.objects.filter(status="LIVE").exists()

    # 2. Sprawdź, czy są mecze zaplanowane, których czas rozpoczęcia
    # jest za mniej niż 15 minut (lub już minął, a my nadal mamy SCHEDULED)
    about_to_start = Match.objects.filter(
        status="SCHEDULED",
        kickoff__lte=time_threshold
    ).exists()

    # Odpytujemy API TYLKO wtedy, gdy dzieje się coś ważnego
    if has_live or about_to_start:
        ImportService.import_matches()