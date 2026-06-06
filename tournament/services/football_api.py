import requests

from django.conf import settings


class FootballDataAPI:

    BASE_URL = "https://api.football-data.org/v4"

    @classmethod
    def get_world_cup_matches(cls):

        headers = {
            "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY
        }

        response = requests.get(
            f"{cls.BASE_URL}/competitions/WC/matches",
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        return response.json()