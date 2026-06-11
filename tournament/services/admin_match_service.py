from django.db.models import Q
from django.utils import timezone

from tournament.models import Match
from tournament.services.scoring_service import ScoringService
from tournament.services.team_name_service import TeamNameService


class AdminMatchService:
    @staticmethod
    def get_first_goal_matches():
        return (
            Match.objects.select_related("home_team", "away_team")
            .filter(
                Q(status__in=["LIVE", "FINISHED"])
                | Q(home_score__isnull=False)
                | Q(away_score__isnull=False)
            )
            .filter(
                Q(first_scoring_team__isnull=True)
                | Q(first_scoring_team="")
                | Q(first_scorer__isnull=True)
                | Q(first_scorer="")
                | Q(first_scoring_team="NONE") & ~Q(first_scorer=ScoringService.NO_SCORER)
                | Q(first_scoring_team__in=["HOME", "AWAY"], first_scorer=ScoringService.NO_SCORER)
            )
            .order_by("-kickoff", "id")
        )

    @classmethod
    def get_first_goal_context(cls, country_language="pl"):
        matches = list(
            cls.get_first_goal_matches()
            .prefetch_related("home_team__players", "away_team__players")
        )
        return {
            "matches": [
                cls._build_first_goal_match_option(match, country_language)
                for match in matches
            ]
        }

    @staticmethod
    def update_first_goal(match_id, first_scoring_team, first_scorer):
        match = (
            Match.objects.select_related("home_team", "away_team")
            .prefetch_related("home_team__players", "away_team__players")
            .get(pk=match_id)
        )
        valid_teams = {choice[0] for choice in Match.TEAM_CHOICES}
        if first_scoring_team and first_scoring_team not in valid_teams:
            raise ValueError("Nieprawidłowa drużyna pierwszego gola.")

        first_scorer = (first_scorer or "").strip()
        if first_scoring_team == "NONE":
            first_scorer = ScoringService.NO_SCORER
        elif first_scorer == ScoringService.NO_SCORER:
            raise ValueError("Brak strzelca można ustawić tylko przy opcji Brak bramek.")

        valid_scorers = {
            player.name
            for player in list(match.home_team.players.all()) + list(match.away_team.players.all())
        }
        if (
            first_scorer
            and first_scorer != ScoringService.NO_SCORER
            and first_scorer not in valid_scorers
        ):
            raise ValueError("Wybierz strzelca z listy zawodników tego meczu.")

        match.first_scoring_team = first_scoring_team or None
        match.first_scorer = first_scorer
        match.save(update_fields=["first_scoring_team", "first_scorer"])
        return match

    @classmethod
    def _build_first_goal_match_option(cls, match, country_language):
        TeamNameService.annotate_match(match, country_language)
        players = sorted(
            list(match.home_team.players.all()) + list(match.away_team.players.all()),
            key=lambda player: (
                TeamNameService.get_team_name(player.team, country_language).lower(),
                player.name.lower(),
            ),
        )
        return {
            "id": match.id,
            "label": cls._format_match_label(match),
            "stage": match.stage,
            "status": match.status,
            "score_label": cls._format_score_label(match),
            "current_first_team": match.first_scoring_team or "",
            "current_first_scorer": cls._get_current_first_scorer(match),
            "no_scorer_value": ScoringService.NO_SCORER,
            "no_scorer_label": ScoringService.NO_SCORER_LABEL,
            "team_choices": [
                {"value": "", "label": "Nie ustawiaj"},
                {"value": "HOME", "label": match.home_team.display_name},
                {"value": "AWAY", "label": match.away_team.display_name},
                {"value": "NONE", "label": "Brak bramek"},
            ],
            "player_choices": [
                {
                    "value": player.name,
                    "label": player.display_label,
                }
                for player in players
            ],
        }

    @staticmethod
    def _get_current_first_scorer(match):
        if match.first_scoring_team == "NONE":
            return ScoringService.NO_SCORER

        return match.first_scorer or ""

    @staticmethod
    def _format_match_label(match):
        kickoff = timezone.localtime(match.kickoff)
        return (
            f"{kickoff:%d.%m.%Y %H:%M} · "
            f"{match.home_team.display_name} vs {match.away_team.display_name}"
        )

    @staticmethod
    def _format_score_label(match):
        if match.home_score is None or match.away_score is None:
            return "Wynik niepełny"

        return f"{match.home_score}:{match.away_score}"
