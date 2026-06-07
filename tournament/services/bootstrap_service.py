from tournament.models import Match, TeamPlayer

from tournament.services.import_service import ImportService
from tournament.services.player_import_service import PlayerImportService
from tournament.services.odds_sync import OddsSync


class BootstrapService:

    @classmethod
    def initialize_database(cls):

        print("Match:", Match.objects.count())
        print("Players:", TeamPlayer.objects.count())

        if not Match.objects.exists():
            print("Import meczów...")
            ImportService.import_matches()

        print("Players po imporcie meczów:",
              TeamPlayer.objects.count())

        if not TeamPlayer.objects.exists():

            print("START IMPORT PLAYERS")

            PlayerImportService.import_players(
                "world_cup_players.json"
            )

            print(
                "KONIEC IMPORT PLAYERS:",
                TeamPlayer.objects.count()
            )

        if Match.objects.filter(
            odds_api_event_id__isnull=True
        ).exists():

            print("Łączenie Odds API...")
            OddsSync.connect_existing_matches()

        print("Aktualizacja kursów...")
        OddsSync.sync_odds()