from django.utils.dateparse import parse_datetime

from tournament.models import Team, Match, Player
from tournament.services.football_api import FootballDataAPI
from tournament.services.scoring_service import ScoringService


class ImportService:
    STATUS_MAPPING = {
        "SCHEDULED": "SCHEDULED",
        "TIMED": "SCHEDULED",
        "IN_PLAY": "LIVE",
        "PAUSED": "LIVE",
        "FINISHED": "FINISHED",
    }

    STAGE_MAPPING = {
        "LAST_32": "1/16 Finału",
        "LAST_16": "1/8 Finału",
        "QUARTER_FINALS": "Ćwierćfinały",
        "SEMI_FINALS": "Półfinały",
        "THIRD_PLACE": "Mecz o 3. miejsce",
        "FINAL": "Finał"
    }

    @classmethod
    def import_matches(cls):
        data = FootballDataAPI.get_world_cup_matches()
        created_matches = 0

        for api_match in data.get("matches", []):
            home = api_match["homeTeam"]
            away = api_match["awayTeam"]

            if not home.get("name") or not away.get("name"):
                continue

            home_team, _ = Team.objects.get_or_create(
                code=home["tla"], defaults={"name": home["name"]}
            )
            away_team, _ = Team.objects.get_or_create(
                code=away["tla"], defaults={"name": away["name"]}
            )

            status = cls.STATUS_MAPPING.get(api_match["status"], "SCHEDULED")

            raw_stage = api_match.get("stage", "GROUP_STAGE")
            matchday = api_match.get("matchday")

            if raw_stage == "GROUP_STAGE" and matchday:
                final_stage_name = f"Runda {matchday}"
            else:
                final_stage_name = cls.STAGE_MAPPING.get(raw_stage, raw_stage)

            home_score = api_match.get("score", {}).get("fullTime", {}).get("home")
            away_score = api_match.get("score", {}).get("fullTime", {}).get("away")

            # 1. Najpierw tworzymy lub aktualizujemy mecz
            match, created = Match.objects.update_or_create(
                home_team=home_team,
                away_team=away_team,
                kickoff=parse_datetime(api_match["utcDate"]),
                defaults={
                    "status": status,
                    "stage": final_stage_name,
                    "home_score": home_score,
                    "away_score": away_score
                }
            )

            lineups = api_match.get("lineups", [])
            for player_data in lineups:
                Player.objects.update_or_create(
                    match=match,
                    name=player_data["player"]["name"],
                    defaults={
                        "team_name": player_data["team"]["name"],
                        "position": player_data.get("position")
                    }
                )

            if created:
                created_matches += 1

            if status in ["LIVE", "FINISHED"]:
                ScoringService.calculate_points_for_match(match)

        return created_matches