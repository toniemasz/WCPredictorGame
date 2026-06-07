import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")

BASE_URL = "https://api.odds-api.io/v3"


class OddsApi:

    @staticmethod
    def get_world_cup_matches():

        response = requests.get(
            "https://api.odds-api.io/v3/events",
            params={
                "apiKey": API_KEY,
                "sport": "football",
                "league": "international-world-cup",
                "limit": 500
            }
        )

        response.raise_for_status()

        events = response.json()

        return [
            event
            for event in events
            if event.get("league", {}).get("slug")
            == "international-world-cup"
        ]

    @staticmethod
    def get_match_odds(event_id):

        response = requests.get(
            f"{BASE_URL}/odds",
            params={
                "apiKey": API_KEY,
                "eventId": event_id,
                "bookmakers": "Bet365"
            }
        )

        response.raise_for_status()

        return response.json()