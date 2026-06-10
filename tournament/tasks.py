from celery import shared_task
from tournament.services.import_service import ImportService
from tournament.services.match_auto_update_service import MatchAutoUpdateService
from tournament.services.odds_sync import OddsSync


@shared_task
def daily_update():
    # To zostawiamy - np. na ściągnięcie planu meczów z samego rana
    ImportService.import_matches()
    OddsSync.connect_existing_matches()
    OddsSync.sync_odds()


@shared_task
def conditional_live_update():
    return MatchAutoUpdateService.check_and_update_matches()
