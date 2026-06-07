from celery import shared_task

from tournament.services.import_service import ImportService
from tournament.services.odds_sync import OddsSync


@shared_task
def daily_update():

    ImportService.import_matches()

    OddsSync.connect_existing_matches()

    OddsSync.sync_odds()


@shared_task
def live_match_update():

    ImportService.import_matches()

@shared_task
def conditional_live_update():

    from tournament.models import Match

    if Match.objects.filter(
        status="LIVE"
    ).exists():

        ImportService.import_matches()