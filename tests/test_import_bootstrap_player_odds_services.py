import json
from datetime import timezone as datetime_timezone
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from tournament.models import ApiSyncStatus, Match, Team, TeamPlayer
from tournament.services.bootstrap_service import BootstrapService
from tournament.services.football_api import FootballDataAPI
from tournament.services.import_service import ImportService
from tournament.services.odds_api import OddsApi
from tournament.services.odds_sync import OddsSync
from tournament.services.player_import_service import PlayerImportService
from tournament.services.scoring_service import ScoringService
from tournament.services.sync_status_service import SyncStatusService


def _api_match(match_id, home_name="Poland", away_name="Germany", **overrides):
    payload = {
        "id": match_id,
        "homeTeam": {"name": home_name, "tla": home_name[:3].upper()},
        "awayTeam": {"name": away_name, "tla": away_name[:3].upper()},
        "status": "SCHEDULED",
        "stage": "GROUP_STAGE",
        "matchday": 1,
        "utcDate": "2026-06-11T19:00:00Z",
        "score": {"fullTime": {"home": None, "away": None}},
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_import_matches_creates_updates_skips_and_records_success(monkeypatch):
    recalculated = []
    data = {
        "matches": [
            _api_match(1),
            _api_match(2, home_name="", away_name="Spain"),
            _api_match(
                3,
                home_name="France",
                away_name="Brazil",
                status="FINISHED",
                stage="FINAL",
                score={"fullTime": {"home": None, "away": None}},
            ),
        ]
    }
    monkeypatch.setattr(FootballDataAPI, "get_world_cup_matches", staticmethod(lambda: data))
    monkeypatch.setattr(
        ScoringService,
        "recalculate_match",
        classmethod(lambda cls, match: recalculated.append(match.football_data_match_id)),
    )

    created = ImportService.import_matches()

    assert created == 2
    assert Match.objects.count() == 2
    assert Match.objects.get(football_data_match_id=1).stage == "Runda 1"
    scheduled_match = Match.objects.get(football_data_match_id=1)
    finished_match = Match.objects.get(football_data_match_id=3)
    assert scheduled_match.last_api_update_at is not None
    assert scheduled_match.final_api_update_at is None
    assert finished_match.stage == "Finał"
    assert finished_match.last_api_update_at is not None
    assert finished_match.final_api_update_at is None
    assert Team.objects.get(name="Germany").name_pl == "Niemcy"
    assert recalculated == [3]

    status = ApiSyncStatus.objects.get(sync_name=ApiSyncStatus.SYNC_MATCHES)
    assert status.status == ApiSyncStatus.STATUS_SUCCESS
    assert status.processed_count == 2
    assert status.created_count == 2

    final_update_at = finished_match.final_api_update_at
    created_again = ImportService.import_matches()
    finished_match.refresh_from_db()

    assert created_again == 0
    assert finished_match.final_api_update_at == final_update_at
    assert ApiSyncStatus.objects.get(sync_name=ApiSyncStatus.SYNC_MATCHES).created_count == 0


@pytest.mark.django_db
def test_import_matches_marks_final_update_only_when_score_is_complete(monkeypatch):
    data = {
        "matches": [
            _api_match(
                10,
                status="FINISHED",
                score={"fullTime": {"home": 2, "away": 0}},
            ),
        ]
    }
    monkeypatch.setattr(FootballDataAPI, "get_world_cup_matches", staticmethod(lambda: data))
    monkeypatch.setattr(
        ScoringService,
        "recalculate_match",
        classmethod(lambda cls, match: None),
    )

    ImportService.import_matches()

    match = Match.objects.get(football_data_match_id=10)
    assert match.status == "FINISHED"
    assert match.home_score == 2
    assert match.away_score == 0
    assert match.final_api_update_at is not None


@pytest.mark.django_db
def test_import_matches_does_not_overwrite_result_with_stale_api_payload(monkeypatch):
    fresh_data = {
        "matches": [
            _api_match(
                11,
                status="FINISHED",
                score={"fullTime": {"home": 2, "away": 0}},
            ),
        ]
    }
    stale_data = {
        "matches": [
            _api_match(
                11,
                status="TIMED",
                score={"fullTime": {"home": None, "away": None}},
            ),
        ]
    }
    responses = iter([fresh_data, stale_data])
    monkeypatch.setattr(FootballDataAPI, "get_world_cup_matches", staticmethod(lambda: next(responses)))
    monkeypatch.setattr(
        ScoringService,
        "recalculate_match",
        classmethod(lambda cls, match: None),
    )

    ImportService.import_matches()
    match = Match.objects.get(football_data_match_id=11)
    final_update_at = match.final_api_update_at

    ImportService.import_matches()
    match.refresh_from_db()

    assert match.status == "FINISHED"
    assert match.home_score == 2
    assert match.away_score == 0
    assert match.final_api_update_at == final_update_at


@pytest.mark.django_db
def test_import_matches_stores_api_kickoff_as_aware_utc_datetime(monkeypatch):
    data = {
        "matches": [
            _api_match(
                99,
                utcDate="2026-06-11T19:00:00Z",
            ),
        ]
    }
    monkeypatch.setattr(FootballDataAPI, "get_world_cup_matches", staticmethod(lambda: data))

    ImportService.import_matches()

    kickoff = Match.objects.get(football_data_match_id=99).kickoff
    assert timezone.is_aware(kickoff)
    assert kickoff.astimezone(datetime_timezone.utc).hour == 19


@pytest.mark.django_db
def test_import_matches_records_error_and_reraises(monkeypatch):
    monkeypatch.setattr(
        FootballDataAPI,
        "get_world_cup_matches",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("football api down"))),
    )

    with pytest.raises(RuntimeError, match="football api down"):
        ImportService.import_matches()

    status = ApiSyncStatus.objects.get(sync_name=ApiSyncStatus.SYNC_MATCHES)
    assert status.status == ApiSyncStatus.STATUS_ERROR
    assert "football api down" in status.last_error


@pytest.mark.django_db
def test_bootstrap_initializes_missing_data(monkeypatch):
    calls = []
    monkeypatch.setattr(ImportService, "import_matches", staticmethod(lambda: calls.append("matches")))
    monkeypatch.setattr(PlayerImportService, "import_players", staticmethod(lambda path: calls.append(("players", path))))
    monkeypatch.setattr(OddsSync, "connect_existing_matches", classmethod(lambda cls: calls.append("connect")))
    monkeypatch.setattr(OddsSync, "sync_odds", classmethod(lambda cls: calls.append("odds")))

    BootstrapService.initialize_database()

    assert "matches" in calls
    assert ("players", "world_cup_players.json") in calls
    assert "odds" in calls
    assert "connect" not in calls


@pytest.mark.django_db
def test_bootstrap_connects_existing_matches_when_odds_id_missing(monkeypatch, future_match, teams):
    TeamPlayer.objects.create(api_player_id=1, team=teams[0], name="Player")
    calls = []
    monkeypatch.setattr(ImportService, "import_matches", staticmethod(lambda: calls.append("matches")))
    monkeypatch.setattr(PlayerImportService, "import_players", staticmethod(lambda path: calls.append("players")))
    monkeypatch.setattr(OddsSync, "connect_existing_matches", classmethod(lambda cls: calls.append("connect")))
    monkeypatch.setattr(OddsSync, "sync_odds", classmethod(lambda cls: calls.append("odds")))

    BootstrapService.initialize_database()

    assert calls == ["connect", "odds"]


@pytest.mark.django_db
def test_player_import_check_team_mapping_returns_missing(tmp_path, teams):
    path = tmp_path / "players.json"
    path.write_text(json.dumps({"Poland": [], "Missingland": []}), encoding="utf-8")

    missing = PlayerImportService.check_team_mapping(path)

    assert missing == ["Missingland"]


@pytest.mark.django_db
def test_player_import_creates_updates_and_skips_players(tmp_path, teams):
    home, _ = teams
    existing = TeamPlayer.objects.create(api_player_id=1, team=home, name="Old")
    path = tmp_path / "players.json"
    path.write_text(
        json.dumps({
            "Poland": [
                {"id": 1, "name": "Updated", "position": "FW", "jersey_number": "9", "nationality": "Poland"},
                {"id": 2, "name": "New", "position": "MF", "jersey_number": "8", "nationality": "Poland"},
            ],
            "Missingland": [
                {"id": 3, "name": "Skipped"},
            ],
        }),
        encoding="utf-8",
    )

    result = PlayerImportService.import_players(path)

    existing.refresh_from_db()
    assert result is None
    assert existing.name == "Updated"
    assert existing.nationality == "Poland"
    assert TeamPlayer.objects.filter(api_player_id=2, name="New").exists()
    assert not TeamPlayer.objects.filter(api_player_id=3).exists()


@pytest.mark.django_db
def test_odds_sync_calls_match_and_odds_sync(monkeypatch):
    calls = []
    monkeypatch.setattr(OddsSync, "sync_matches", classmethod(lambda cls: calls.append("matches")))
    monkeypatch.setattr(OddsSync, "sync_odds", classmethod(lambda cls: calls.append("odds")))

    OddsSync.sync()

    assert calls == ["matches", "odds"]


@pytest.mark.django_db
def test_odds_sync_sync_matches_creates_matches(monkeypatch):
    events = [
        {"id": 10, "home": "Team Alpha", "away": "Team Beta", "status": "live", "date": "2026-06-11T19:00:00Z"},
        {"id": 11, "home": "Team Gamma", "away": "Team Delta", "status": "settled", "date": "2026-06-12T19:00:00Z"},
    ]
    monkeypatch.setattr(OddsApi, "get_world_cup_matches", staticmethod(lambda: events))

    OddsSync.sync_matches()

    assert Match.objects.get(odds_api_event_id=10).status == "LIVE"
    assert Match.objects.get(odds_api_event_id=11).status == "FINISHED"


@pytest.mark.django_db
def test_odds_sync_sync_odds_updates_only_valid_moneyline(monkeypatch, make_match):
    match = make_match(
        kickoff=timezone.now() + timedelta(days=2),
        odds_api_event_id=123,
    )
    monkeypatch.setattr(
        OddsApi,
        "get_match_odds",
        staticmethod(lambda event_id: {
            "bookmakers": {
                "Bet365": [
                    {"name": "ML", "odds": [{"home": "1.50", "draw": "3.00", "away": "6.00"}]}
                ]
            }
        }),
    )

    OddsSync.sync_odds()
    match.refresh_from_db()

    assert str(match.home_odds) == "1.50"
    assert str(match.draw_odds) == "3.00"
    assert str(match.away_odds) == "6.00"


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [
    {"bookmakers": {}},
    {"bookmakers": {"Bet365": [{"name": "SPREAD", "odds": []}]}},
])
def test_odds_sync_sync_odds_skips_missing_market(monkeypatch, make_match, payload):
    match = make_match(
        kickoff=timezone.now() + timedelta(days=2),
        odds_api_event_id=123,
        home_odds=None,
        draw_odds=None,
        away_odds=None,
    )
    monkeypatch.setattr(OddsApi, "get_match_odds", staticmethod(lambda event_id: payload))

    OddsSync.sync_odds()
    match.refresh_from_db()

    assert match.home_odds is None
    assert match.draw_odds is None
    assert match.away_odds is None


@pytest.mark.django_db
def test_odds_sync_sync_odds_swallows_api_errors(monkeypatch, make_match):
    match = make_match(kickoff=timezone.now() + timedelta(days=2), odds_api_event_id=123)
    monkeypatch.setattr(
        OddsApi,
        "get_match_odds",
        staticmethod(lambda event_id: (_ for _ in ()).throw(RuntimeError("bad odds"))),
    )

    OddsSync.sync_odds()
    match.refresh_from_db()

    assert str(match.home_odds) == "4.20"


@pytest.mark.django_db
def test_odds_sync_connect_existing_matches_updates_matching_match(monkeypatch, teams, make_match):
    match = make_match(
        home_team=teams[0],
        away_team=teams[1],
        kickoff=timezone.datetime(2026, 6, 11, 19, tzinfo=timezone.UTC),
        odds_api_event_id=None,
    )
    events = [
        {"id": 777, "home": "Poland", "away": "Germany", "date": "2026-06-11T19:00:00Z"},
        {"id": 778, "home": "USA", "away": "Missing", "date": "2026-06-11T19:00:00Z"},
    ]
    monkeypatch.setattr(OddsApi, "get_world_cup_matches", staticmethod(lambda: events))

    OddsSync.connect_existing_matches()
    match.refresh_from_db()

    assert match.odds_api_event_id == 777
