from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tournament.models import Match, Team
from tournament.services.odds_api import OddsApi


class OddsSync:

    BOOKMAKER = "Bet365"

    @classmethod
    def sync(cls):

        print("=== Sync matches ===")
        cls.sync_matches()

        print("=== Sync odds ===")
        cls.sync_odds()

    @classmethod
    def sync_matches(cls):

        events = OddsApi.get_world_cup_matches()

        for event in events:
            home_team = cls._get_or_create_team(event["home"])
            away_team = cls._get_or_create_team(event["away"])

            Match.objects.update_or_create(
                odds_api_event_id=event["id"],
                defaults={
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff": parse_datetime(
                        event["date"]
                    ),
                    "status": cls._get_status(event)
                }
            )

            print(
                f'Sync match: '
                f'{event["home"]} vs {event["away"]}'
            )

    @classmethod
    def sync_odds(cls):

        matches = Match.objects.filter(
            kickoff__gte=timezone.now(),
            kickoff__lte=timezone.now() + timedelta(days=10)
        ).exclude(
            odds_api_event_id__isnull=True
        )
        for match in matches:

            try:

                data = OddsApi.get_match_odds(
                    match.odds_api_event_id
                )

                odds = cls._extract_moneyline_odds(data)
                if not odds:
                    continue

                cls._update_match_odds(match, odds)

                print(
                    f'Updated odds: '
                    f'{match.home_team.name} '
                    f'vs '
                    f'{match.away_team.name}'
                )

            except Exception as e:

                print(
                    f'Odds error '
                    f'{match.odds_api_event_id}: '
                    f'{e}'
                )

    TEAM_MAPPING = {
        "Korea Republic": "South Korea",
        "IR Iran": "Iran",
        "Turkiye": "Turkey",
        "Curacao": "Curaçao",
        "Cape Verde": "Cape Verde Islands",
        "Bosnia and Herzegovina": "Bosnia-Herzegovina",
        "USA": "United States",
    }

    @classmethod
    def connect_existing_matches(cls):


            events = OddsApi.get_world_cup_matches()

            connected = 0

            for event in events:

                match = cls._find_existing_match(event)

                if not match:
                    print(
                        f'Nie znaleziono: '
                        f'{event["home"]} vs {event["away"]}'
                    )
                    continue

                if match.odds_api_event_id != event["id"]:

                    match.odds_api_event_id = event["id"]

                    match.save(
                        update_fields=[
                            "odds_api_event_id"
                        ]
                    )

                    connected += 1

                    print(
                        f'Połączono: '
                        f'{match.home_team.name} '
                        f'vs '
                        f'{match.away_team.name}'
                    )

            print(
                f'Połączono meczów: {connected}'
            )

    @staticmethod
    def _get_or_create_team(team_name):
        team, _ = Team.objects.get_or_create(
            name=team_name,
            defaults={
                "code": OddsSync._build_unique_team_code(team_name)
            }
        )
        return team

    @staticmethod
    def _build_unique_team_code(team_name):
        base_code = team_name[:3].upper()

        if not Team.objects.filter(code=base_code).exclude(name=team_name).exists():
            return base_code

        for number in range(1, 10):
            code = f"{base_code[:2]}{number}"
            if not Team.objects.filter(code=code).exists():
                return code

        return base_code

    @staticmethod
    def _get_status(event):
        if event["status"] == "live":
            return "LIVE"
        if event["status"] == "settled":
            return "FINISHED"
        return "SCHEDULED"

    @classmethod
    def _extract_moneyline_odds(cls, data):
        bookmaker_markets = data["bookmakers"].get(
            cls.BOOKMAKER
        )

        if not bookmaker_markets:
            return None

        for market in bookmaker_markets:
            if market["name"] == "ML":
                return market["odds"][0]

        return None

    @staticmethod
    def _update_match_odds(match, odds):
        match.home_odds = odds["home"]
        match.draw_odds = odds["draw"]
        match.away_odds = odds["away"]

        match.save(
            update_fields=[
                "home_odds",
                "draw_odds",
                "away_odds"
            ]
        )

    @classmethod
    def _normalize_team_name(cls, name):
        return cls.TEAM_MAPPING.get(name, name)

    @classmethod
    def _find_existing_match(cls, event):
        kickoff = parse_datetime(event["date"])

        return Match.objects.filter(
            home_team__name__iexact=cls._normalize_team_name(event["home"]),
            away_team__name__iexact=cls._normalize_team_name(event["away"]),
            kickoff=kickoff
        ).first()
