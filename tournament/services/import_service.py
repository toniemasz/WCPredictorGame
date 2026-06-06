from django.utils.dateparse import parse_datetime

from tournament.models import Team, Match
from tournament.services.football_api import FootballDataAPI


class ImportService:

    STATUS_MAPPING = {
        "SCHEDULED": "SCHEDULED",
        "TIMED": "SCHEDULED",
        "IN_PLAY": "LIVE",
        "PAUSED": "LIVE",
        "FINISHED": "FINISHED",
    }

    @classmethod
    def import_matches(cls):

        data = FootballDataAPI.get_world_cup_matches()

        created_matches = 0

        for api_match in data["matches"]:

            home = api_match["homeTeam"]
            away = api_match["awayTeam"]

            if not home.get("name") or not away.get("name"):
                continue

            home_team, _ = Team.objects.get_or_create(
                code=home["tla"],
                defaults={
                    "name": home["name"]
                }
            )

            away_team, _ = Team.objects.get_or_create(
                code=away["tla"],
                defaults={
                    "name": away["name"]
                }
            )

            match, created = Match.objects.get_or_create(
                home_team=home_team,
                away_team=away_team,
                kickoff=parse_datetime(api_match["utcDate"]),
                defaults={
                    "status": cls.STATUS_MAPPING.get(
                        api_match["status"],
                        "SCHEDULED"
                    )
                }
            )

            if created:
                created_matches += 1

        return created_matches