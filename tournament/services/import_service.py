from datetime import timezone as datetime_timezone

from django.utils import timezone
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
    STATUS_PROGRESS = {
        "SCHEDULED": 0,
        "LIVE": 1,
        "FINISHED": 2,
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
            data = cls._fetch_matches()
        except Exception as error:
            SyncStatusService.record_error(ApiSyncStatus.SYNC_MATCHES, error)
            raise

        created_matches = 0
        processed_matches = 0

        for api_match in data.get("matches", []):
            if not cls._has_named_teams(api_match):
                continue

            processed_matches += 1
            match, created = cls._update_match_from_api(api_match)

            if created:
                created_matches += 1

            if match.status in ["LIVE", "FINISHED"]:
                ScoringService.recalculate_match(match)

        SyncStatusService.record_success(
            ApiSyncStatus.SYNC_MATCHES,
            processed_count=processed_matches,
            created_count=created_matches,
        )

        return created_matches

    @staticmethod
    def _fetch_matches():
        return FootballDataAPI.get_world_cup_matches()

    @staticmethod
    def _parse_api_datetime(value):
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValueError(f"Nieprawidłowa data meczu z API: {value}")
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, datetime_timezone.utc)
        return parsed.astimezone(datetime_timezone.utc)

    @staticmethod
    def _has_named_teams(api_match):
        home = api_match["homeTeam"]
        away = api_match["awayTeam"]
        return bool(home.get("name") and away.get("name"))

    @classmethod
    def _update_match_from_api(cls, api_match):
        home_team = cls._get_or_create_team(api_match["homeTeam"])
        away_team = cls._get_or_create_team(api_match["awayTeam"])
        existing_match = cls._get_existing_match(api_match["id"])
        api_home_score, api_away_score = cls._get_full_time_score(api_match)
        home_score, away_score = cls._resolve_score(
            existing_match,
            api_home_score,
            api_away_score,
        )
        status = cls._resolve_status(
            existing_match,
            cls._get_status(api_match),
        )
        update_time = timezone.now()
        final_update_time = cls._get_final_update_time(
            existing_match,
            status,
            home_score,
            away_score,
            update_time,
        )

        return Match.objects.update_or_create(
            football_data_match_id=api_match["id"],
            defaults={
                "home_team": home_team,
                "away_team": away_team,
                "kickoff": cls._parse_api_datetime(api_match["utcDate"]),
                "status": status,
                "stage": cls._get_stage_name(api_match),
                "home_score": home_score,
                "away_score": away_score,
                "last_api_update_at": update_time,
                "final_api_update_at": final_update_time,
            }
        )

    @staticmethod
    def _get_existing_match(api_match_id):
        return Match.objects.filter(
            football_data_match_id=api_match_id
        ).first()

    @classmethod
    def _resolve_score(cls, existing_match, api_home_score, api_away_score):
        if cls._has_complete_score(api_home_score, api_away_score):
            return api_home_score, api_away_score

        if existing_match and cls._has_complete_score(
            existing_match.home_score,
            existing_match.away_score,
        ):
            return existing_match.home_score, existing_match.away_score

        return api_home_score, api_away_score

    @classmethod
    def _resolve_status(cls, existing_match, api_status):
        if not existing_match:
            return api_status

        existing_progress = cls.STATUS_PROGRESS.get(existing_match.status, 0)
        api_progress = cls.STATUS_PROGRESS.get(api_status, 0)

        if existing_progress > api_progress:
            return existing_match.status

        return api_status

    @classmethod
    def _get_final_update_time(
        cls,
        existing_match,
        status,
        home_score,
        away_score,
        update_time,
    ):
        if existing_match and existing_match.final_api_update_at:
            return existing_match.final_api_update_at

        if status != "FINISHED" or not cls._has_complete_score(home_score, away_score):
            return None

        return update_time

    @classmethod
    def _get_or_create_team(cls, api_team):
        team, _ = Team.objects.get_or_create(
            code=api_team["tla"],
            defaults={"name": api_team["name"]}
        )
        cls._sync_team_translation(team)
        return team

    @classmethod
    def _sync_team_translation(cls, team):
        if team.name_pl:
            return

        team.name_pl = cls.COUNTRY_TRANSLATIONS.get(
            team.name,
            team.name
        )
        team.save(update_fields=["name_pl"])

    @classmethod
    def _get_status(cls, api_match):
        return cls.STATUS_MAPPING.get(api_match["status"], "SCHEDULED")

    @classmethod
    def _get_stage_name(cls, api_match):
        raw_stage = api_match.get("stage", "GROUP_STAGE")
        matchday = api_match.get("matchday")

        if raw_stage == "GROUP_STAGE" and matchday:
            return f"Runda {matchday}"

        return cls.STAGE_MAPPING.get(raw_stage, raw_stage)

    @staticmethod
    def _get_full_time_score(api_match):
        score = api_match.get("score", {}).get("fullTime", {})
        return score.get("home"), score.get("away")

    @staticmethod
    def _has_complete_score(home_score, away_score):
        return home_score is not None and away_score is not None
