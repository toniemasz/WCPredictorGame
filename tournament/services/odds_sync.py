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

            home_name = event["home"]
            away_name = event["away"]

            home_team, _ = Team.objects.get_or_create(
                name=home_name,
                defaults={
                    "code": home_name[:3].upper()
                }
            )

            away_team, _ = Team.objects.get_or_create(
                name=away_name,
                defaults={
                    "code": away_name[:3].upper()
                }
            )

            status = "SCHEDULED"

            if event["status"] == "live":
                status = "LIVE"

            elif event["status"] == "settled":
                status = "FINISHED"

            Match.objects.update_or_create(
                odds_api_event_id=event["id"],
                defaults={
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff": parse_datetime(
                        event["date"]
                    ),
                    "status": status
                }
            )

            print(
                f'Sync match: '
                f'{home_name} vs {away_name}'
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

                bookmaker_markets = data["bookmakers"].get(
                    cls.BOOKMAKER
                )

                if not bookmaker_markets:
                    continue

                ml_market = None

                for market in bookmaker_markets:

                    if market["name"] == "ML":
                        ml_market = market
                        break

                if not ml_market:
                    continue

                odds = ml_market["odds"][0]

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

                home_name = cls.TEAM_MAPPING.get(
                    event["home"],
                    event["home"]
                )

                away_name = cls.TEAM_MAPPING.get(
                    event["away"],
                    event["away"]
                )

                kickoff = parse_datetime(event["date"])

                match = Match.objects.filter(
                    home_team__name__iexact=home_name,
                    away_team__name__iexact=away_name,
                    kickoff=kickoff
                ).first()

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