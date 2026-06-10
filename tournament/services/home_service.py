from copy import deepcopy

from django.conf import settings

from tournament.content.home_page import HOME_PAGE_CONTENT
from tournament.services.scoring_service import (
    correct_first_scorer_points,
    correct_first_team_scored,
    correct_goal_diff_points,
    correct_home_or_away_goals_points,
    correct_home_or_away_win_points,
    correct_result_points,
)
from tournament.services.sync_status_service import SyncStatusService


class HomePageService:
    @classmethod
    def get_context(cls):
        content = deepcopy(HOME_PAGE_CONTENT)

        return {
            "home_content": cls._format_content(content),
            "matches_sync": SyncStatusService.get_matches_sync_info(),
        }

    @classmethod
    def _format_content(cls, value):
        if isinstance(value, str):
            return value.format(**cls._format_values())

        if isinstance(value, list):
            return [cls._format_content(item) for item in value]

        if isinstance(value, dict):
            return {
                key: cls._format_content(item)
                for key, item in value.items()
            }

        return value

    @staticmethod
    def _format_values():
        return {
            "bonus_limit": getattr(settings, "BONUS_LIMIT_PER_STAGE", 2),
            "correct_result_points": correct_result_points,
            "correct_home_or_away_goals_points": correct_home_or_away_goals_points,
            "correct_goal_diff_points": correct_goal_diff_points,
            "correct_home_or_away_win_points": correct_home_or_away_win_points,
            "correct_first_scorer_points": correct_first_scorer_points,
            "correct_first_team_scored": correct_first_team_scored,
        }
