from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from tournament.models import Match, Team


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="pass")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other", password="pass")


@pytest.fixture
def teams(db):
    home = Team.objects.create(name="Poland", code="POL", name_pl="Polska")
    away = Team.objects.create(name="Germany", code="GER", name_pl="Niemcy")
    return home, away


@pytest.fixture
def make_match(db, teams):
    def _make_match(**overrides):
        home, away = teams
        defaults = {
            "home_team": home,
            "away_team": away,
            "kickoff": timezone.now() + timedelta(days=1),
            "status": "SCHEDULED",
            "stage": "Runda 1",
            "home_score": None,
            "away_score": None,
            "home_odds": Decimal("4.20"),
            "draw_odds": Decimal("3.50"),
            "away_odds": Decimal("1.70"),
            "first_scoring_team": "HOME",
            "first_scorer": "Lewandowski",
        }
        defaults.update(overrides)
        return Match.objects.create(**defaults)

    return _make_match


@pytest.fixture
def future_match(make_match):
    return make_match()


@pytest.fixture
def finished_match(make_match):
    return make_match(
        kickoff=timezone.now() - timedelta(days=1),
        status="FINISHED",
        home_score=2,
        away_score=1,
    )
