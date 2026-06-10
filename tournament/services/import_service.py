from django.utils.dateparse import parse_datetime

from tournament.models import ApiSyncStatus, Match, Team
from tournament.services.football_api import FootballDataAPI
from tournament.services.scoring_service import ScoringService
from tournament.services.sync_status_service import SyncStatusService


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

    COUNTRY_TRANSLATIONS = {
        "Algeria": "Algieria",
        "Argentina": "Argentyna",
        "Australia": "Australia",
        "Austria": "Austria",
        "Belgium": "Belgia",
        "Bosnia-Herzegovina": "Bośnia i Hercegowina",
        "Brazil": "Brazylia",
        "Canada": "Kanada",
        "Cape Verde Islands": "Republika Zielonego Przylądka",
        "Colombia": "Kolumbia",
        "Congo DR": "Demokratyczna Republika Konga",
        "Croatia": "Chorwacja",
        "Curaçao": "Curaçao",
        "Czechia": "Czechy",
        "Ecuador": "Ekwador",
        "Egypt": "Egipt",
        "England": "Anglia",
        "France": "Francja",
        "Germany": "Niemcy",
        "Ghana": "Ghana",
        "Haiti": "Haiti",
        "Iran": "Iran",
        "Iraq": "Irak",
        "Ivory Coast": "Wybrzeże Kości Słoniowej",
        "Japan": "Japonia",
        "Jordan": "Jordania",
        "Mexico": "Meksyk",
        "Morocco": "Maroko",
        "Netherlands": "Holandia",
        "New Zealand": "Nowa Zelandia",
        "Norway": "Norwegia",
        "Panama": "Panama",
        "Paraguay": "Paragwaj",
        "Portugal": "Portugalia",
        "Qatar": "Katar",
        "Saudi Arabia": "Arabia Saudyjska",
        "Scotland": "Szkocja",
        "Senegal": "Senegal",
        "South Africa": "Republika Południowej Afryki",
        "South Korea": "Korea Południowa",
        "Spain": "Hiszpania",
        "Sweden": "Szwecja",
        "Switzerland": "Szwajcaria",
        "Tunisia": "Tunezja",
        "Turkey": "Turcja",
        "United States": "Stany Zjednoczone",
        "Uruguay": "Urugwaj",
        "Uzbekistan": "Uzbekistan",
    }

    @classmethod
    def import_matches(cls):
        SyncStatusService.record_attempt(ApiSyncStatus.SYNC_MATCHES)

        try:
            data = FootballDataAPI.get_world_cup_matches()
        except Exception as error:
            SyncStatusService.record_error(ApiSyncStatus.SYNC_MATCHES, error)
            raise

        created_matches = 0
        processed_matches = 0

        for api_match in data.get("matches", []):
            home = api_match["homeTeam"]
            away = api_match["awayTeam"]

            if not home.get("name") or not away.get("name"):
                continue

            processed_matches += 1

            home_team, _ = Team.objects.get_or_create(
                code=home["tla"], defaults={"name": home["name"]}
            )
            away_team, _ = Team.objects.get_or_create(
                code=away["tla"], defaults={"name": away["name"]}
            )

            for team in [home_team, away_team]:
                if not team.name_pl:
                    team.name_pl = cls.COUNTRY_TRANSLATIONS.get(
                        team.name,
                        team.name
                    )
                    team.save(update_fields=["name_pl"])

            status = cls.STATUS_MAPPING.get(api_match["status"], "SCHEDULED")

            raw_stage = api_match.get("stage", "GROUP_STAGE")
            matchday = api_match.get("matchday")

            if raw_stage == "GROUP_STAGE" and matchday:
                final_stage_name = f"Runda {matchday}"
            else:
                final_stage_name = cls.STAGE_MAPPING.get(raw_stage, raw_stage)

            home_score = api_match.get("score", {}).get("fullTime", {}).get("home")
            away_score = api_match.get("score", {}).get("fullTime", {}).get("away")

            match, created = Match.objects.update_or_create(
                football_data_match_id=api_match["id"],
                defaults={
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff": parse_datetime(api_match["utcDate"]),
                    "status": status,
                    "stage": final_stage_name,
                    "home_score": home_score,
                    "away_score": away_score
                }
            )


            if created:
                created_matches += 1

            if status in ["LIVE", "FINISHED"]:
                ScoringService.recalculate_match(match)

        SyncStatusService.record_success(
            ApiSyncStatus.SYNC_MATCHES,
            processed_count=processed_matches,
            created_count=created_matches,
        )

        return created_matches
