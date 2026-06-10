from copy import deepcopy

from django.conf import settings

from tournament.content.home_page import HOME_PAGE_CONTENT
from tournament.services.scoring_service import ScoringService
from tournament.services.sync_status_service import SyncStatusService


class HomePageService:
    @classmethod
    def get_context(cls):
        content = deepcopy(HOME_PAGE_CONTENT)
        cls._inject_scoring_rules(content)

        return {
            "home_content": cls._format_content(content),
            "matches_sync": SyncStatusService.get_matches_sync_info(),
        }

    @classmethod
    def _inject_scoring_rules(cls, content):
        scoring_section = cls._get_scoring_section(content)
        if scoring_section:
            scoring_section["items"] = cls._get_scoring_rule_items()

    @staticmethod
    def _get_scoring_section(content):
        sections = content.get("game_info", {}).get("sections", [])
        return next(
            (
                section
                for section in sections
                if section.get("title") == "Punktacja"
            ),
            None,
        )

    @staticmethod
    def _get_scoring_rule_items():
        lines = ScoringService.get_rules_explanation().splitlines()
        return [
            line.removeprefix("• ").strip()
            for line in lines
            if line.strip() and not line.startswith("Zasady punktacji")
        ]

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
        }
