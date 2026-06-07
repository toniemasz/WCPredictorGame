from tournament.models import Match, TeamPlayer

from tournament.services.import_service import ImportService
from tournament.services.player_import_service import PlayerImportService
from tournament.services.odds_sync import OddsSync


class BootstrapService:

    @classmethod
    def initialize_database(cls):

        if not Match.objects.exists():
            print("Import meczów...")
            ImportService.import_matches()

        if not TeamPlayer.objects.exists():
            print("Import zawodników...")
            PlayerImportService.import_players(
                "world_cup_players.json"
            )

        if Match.objects.filter(
            odds_api_event_id__isnull=True
        ).exists():

            print("Łączenie Odds API...")
            OddsSync.connect_existing_matches()

        print("Aktualizacja kursów...")
        OddsSync.sync_odds()