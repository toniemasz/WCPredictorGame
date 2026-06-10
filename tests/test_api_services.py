from unittest.mock import Mock, patch

import pytest
from django.conf import settings

from tournament.services.football_api import FootballDataAPI
from tournament.services.odds_api import OddsApi


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.raise_for_status = Mock(side_effect=error)

    def json(self):
        return self.payload


def test_football_data_api_returns_matches_and_uses_auth_header():
    response = FakeResponse({"matches": [{"id": 1}]})

    with patch("tournament.services.football_api.requests.get", return_value=response) as request:
        payload = FootballDataAPI.get_world_cup_matches()

    assert payload == {"matches": [{"id": 1}]}
    request.assert_called_once_with(
        f"{FootballDataAPI.BASE_URL}/competitions/WC/matches",
        headers={"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY},
        timeout=10,
    )
    response.raise_for_status.assert_called_once()


def test_football_data_api_raises_for_bad_response():
    response = FakeResponse(error=RuntimeError("api down"))

    with patch("tournament.services.football_api.requests.get", return_value=response):
        with pytest.raises(RuntimeError, match="api down"):
            FootballDataAPI.get_world_cup_matches()


def test_odds_api_filters_only_world_cup_events():
    response = FakeResponse([
        {"id": 1, "league": {"slug": "international-world-cup"}},
        {"id": 2, "league": {"slug": "other"}},
        {"id": 3, "league": {}},
    ])

    with patch("tournament.services.odds_api.requests.get", return_value=response) as request:
        events = OddsApi.get_world_cup_matches()

    assert events == [{"id": 1, "league": {"slug": "international-world-cup"}}]
    request.assert_called_once()
    response.raise_for_status.assert_called_once()


def test_odds_api_get_match_odds_returns_payload():
    response = FakeResponse({"bookmakers": {}})

    with patch("tournament.services.odds_api.requests.get", return_value=response) as request:
        payload = OddsApi.get_match_odds(123)

    assert payload == {"bookmakers": {}}
    assert request.call_args.kwargs["params"]["eventId"] == 123
    response.raise_for_status.assert_called_once()


def test_odds_api_get_match_odds_raises_for_bad_response():
    response = FakeResponse(error=RuntimeError("odds api down"))

    with patch("tournament.services.odds_api.requests.get", return_value=response):
        with pytest.raises(RuntimeError, match="odds api down"):
            OddsApi.get_match_odds(123)
