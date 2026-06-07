from django.utils.dateparse import parse_datetime

from tournament.models import Team, Match
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

    # Słownik dla faz pucharowych
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

            # MAGIA Z RUNDAMI:
            raw_stage = api_match.get("stage", "GROUP_STAGE")
            matchday = api_match.get("matchday")

            # Jeśli to faza grupowa, nazywamy to "Runda X" na podstawie kolejki (matchday)
            if raw_stage == "GROUP_STAGE" and matchday:
                final_stage_name = f"Runda {matchday}"
            else:
                # W przeciwnym razie to faza pucharowa, tłumaczymy ze słownika
                final_stage_name = cls.STAGE_MAPPING.get(raw_stage, raw_stage)

            home_score = api_match.get("score", {}).get("fullTime", {}).get("home")
            away_score = api_match.get("score", {}).get("fullTime", {}).get("away")

            match, created = Match.objects.update_or_create(
                home_team=home_team,
                away_team=away_team,
                kickoff=parse_datetime(api_match["utcDate"]),
                defaults={
                    "status": status,
                    "stage": final_stage_name,  # Zapisujemy "Runda 1", "Runda 2", "1/8 Finału" itd.
                    "home_score": home_score,
                    "away_score": away_score
                }
            )

            if created:
                created_matches += 1

            if status in ["LIVE", "FINISHED"]:
                ScoringService.calculate_points_for_match(match)

        return created_matches