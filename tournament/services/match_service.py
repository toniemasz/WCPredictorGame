from django.conf import settings
from django.db.models import Count
from django.shortcuts import get_object_or_404

from tournament.models import BonusUsage, Match, Prediction, Profile
from tournament.services.import_service import ImportService
from tournament.services.profile_service import ProfileService
from tournament.services.scoring_service import ScoringService


class MatchListService:
    @staticmethod
    def get_match_list_context(user):
        if Match.objects.count() == 0:
            ImportService.import_matches()

        matches = Match.objects.select_related(
            "home_team", "away_team"
        ).prefetch_related(
            "home_team__players", "away_team__players"
        ).order_by("kickoff")

        predictions = Prediction.objects.filter(user=user)
        predictions_by_match_id = {
            prediction.match_id: prediction
            for prediction in predictions
        }

        bonus_usages = BonusUsage.objects.filter(user=user)
        bonus_count_by_stage = {
            bonus.stage: bonus.count
            for bonus in bonus_usages
        }

        prediction_count_by_match_id = {
            item["match_id"]: item["count"]
            for item in Prediction.objects.values("match_id").annotate(count=Count("id"))
        }

        bonus_limit = getattr(settings, "BONUS_LIMIT_PER_STAGE", 2)
        matches_by_stage = {}
        summary = {
            "total_matches": 0,
            "predicted_matches": 0,
            "incomplete_predictions": 0,
            "scheduled_matches": 0,
            "live_matches": 0,
            "finished_matches": 0,
        }

        for match in matches:
            user_prediction = predictions_by_match_id.get(match.id)
            used_bonus_count = bonus_count_by_stage.get(match.stage, 0)
            remaining_bonus_count = bonus_limit - used_bonus_count

            missing_options = MatchListService._get_missing_prediction_options(
                user_prediction
            )

            match.user_prediction = user_prediction
            match.has_prediction = user_prediction is not None
            match.missing_prediction_options = missing_options
            match.has_incomplete_prediction = bool(missing_options)
            match.bonus_remaining = remaining_bonus_count
            match.is_bonus_locked = (
                remaining_bonus_count <= 0
                and not (user_prediction and user_prediction.is_doubled)
            )
            match.can_view_public_predictions = match.status in ["LIVE", "FINISHED"]
            match.public_predictions_count = prediction_count_by_match_id.get(match.id, 0)
            match.available_players = (
                list(match.home_team.players.all())
                + list(match.away_team.players.all())
            )

            matches_by_stage.setdefault(match.stage, []).append(match)

            summary["total_matches"] += 1
            if user_prediction:
                summary["predicted_matches"] += 1
            if missing_options:
                summary["incomplete_predictions"] += 1
            if match.status == "LIVE":
                summary["live_matches"] += 1
            elif match.status == "FINISHED":
                summary["finished_matches"] += 1
            else:
                summary["scheduled_matches"] += 1

        stage_groups = MatchListService._build_stage_groups(matches_by_stage)
        active_stage_id = MatchListService._get_active_stage_id(stage_groups)
        for stage in stage_groups:
            stage["is_active"] = stage["id"] == active_stage_id

        return {
            "rules_explanation": ScoringService.get_rules_explanation(),
            "matches_by_stage": matches_by_stage,
            "stage_groups": stage_groups,
            "active_stage_id": active_stage_id,
            "summary": summary,
            "bonus_limit": bonus_limit,
        }

    @staticmethod
    def get_public_predictions_context(match_id):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            pk=match_id
        )

        if match.status not in ["LIVE", "FINISHED"]:
            raise ValueError("Typy innych graczy będą widoczne po rozpoczęciu meczu.")

        predictions = list(
            Prediction.objects.select_related("user", "user__profile")
            .filter(match=match)
            .order_by("-points", "user__username")
        )

        for prediction in predictions:
            profile, _ = Profile.objects.get_or_create(user=prediction.user)
            prediction.avatar_url = ProfileService.get_avatar_url(
                profile.avatar
            )
            prediction.missing_options = MatchListService._get_missing_prediction_options(
                prediction
            )
            prediction.first_team_label = MatchListService._get_first_team_label(
                match,
                prediction.predicted_first_team,
            )

        return {
            "match": match,
            "predictions": predictions,
            "total_predictions": len(predictions),
        }

    @staticmethod
    def _build_stage_groups(matches_by_stage):
        stage_groups = []

        for index, (stage_name, stage_matches) in enumerate(matches_by_stage.items(), start=1):
            total_matches = len(stage_matches)
            predicted_matches = sum(1 for match in stage_matches if match.has_prediction)
            incomplete_predictions = sum(
                1 for match in stage_matches if match.has_incomplete_prediction
            )
            live_matches = sum(1 for match in stage_matches if match.status == "LIVE")
            finished_matches = sum(
                1 for match in stage_matches if match.status == "FINISHED"
            )
            scheduled_matches = total_matches - live_matches - finished_matches

            stage_groups.append({
                "id": f"stage-{index}",
                "name": stage_name,
                "matches": stage_matches,
                "total_matches": total_matches,
                "predicted_matches": predicted_matches,
                "incomplete_predictions": incomplete_predictions,
                "live_matches": live_matches,
                "finished_matches": finished_matches,
                "scheduled_matches": scheduled_matches,
                "status_label": MatchListService._get_stage_status_label(
                    scheduled_matches,
                    live_matches,
                    finished_matches,
                    total_matches,
                ),
            })

        return stage_groups

    @staticmethod
    def _get_active_stage_id(stage_groups):
        for stage in stage_groups:
            if stage["live_matches"] or stage["scheduled_matches"]:
                return stage["id"]

        if stage_groups:
            return stage_groups[-1]["id"]

        return None

    @staticmethod
    def _get_stage_status_label(scheduled_matches, live_matches, finished_matches, total_matches):
        if live_matches:
            return "LIVE"

        if finished_matches == total_matches and total_matches:
            return "Zakończona"

        if scheduled_matches:
            return "Do obstawienia"

        return "W przygotowaniu"

    @staticmethod
    def _get_missing_prediction_options(prediction):
        if not prediction:
            return []

        missing_options = []

        if not prediction.predicted_first_team:
            missing_options.append("pierwsza drużyna z golem")

        if not prediction.predicted_scorer:
            missing_options.append("pierwszy strzelec")

        return missing_options

    @staticmethod
    def _get_first_team_label(match, value):
        if value == "HOME":
            return match.home_team.name_pl or match.home_team.name
        if value == "AWAY":
            return match.away_team.name_pl or match.away_team.name
        if value == "NONE":
            return "Brak bramek"
        return "-"
