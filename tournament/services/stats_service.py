from collections import defaultdict

from django.contrib.auth.models import User
from django.db.models import Max, Min

from tournament.models import Match, Prediction
from tournament.services.scoring_service import ScoringService
from tournament.services.team_name_service import TeamNameService


class StatsService:
    MIN_EFFECTIVENESS_RATIO = 0.5

    @classmethod
    def is_stage_finished(cls, stage):
        matches = list(Match.objects.filter(stage=stage))
        if not matches:
            return False

        return all(cls._match_is_finished(match) for match in matches)

    @classmethod
    def get_finished_stages(cls):
        stage_rows = (
            Match.objects.values("stage")
            .annotate(first_kickoff=Min("kickoff"), last_kickoff=Max("kickoff"))
            .order_by("first_kickoff", "stage")
        )

        return [
            row["stage"]
            for row in stage_rows
            if cls.is_stage_finished(row["stage"])
        ]

    @classmethod
    def get_latest_completed_stage(cls):
        stages = cls.get_finished_stages()
        if not stages:
            return None
        return stages[-1]

    @classmethod
    def get_user_stats(cls, user, stage, country_language="pl"):
        matches = cls._get_stage_matches(stage)
        predictions = cls._get_user_predictions(user, stage)
        predictions_by_match = {
            prediction.match_id: prediction
            for prediction in predictions
        }
        total_matches = len(matches)
        predicted_count = len(predictions)
        missing_count = max(total_matches - predicted_count, 0)

        exact_count = 0
        outcome_count = 0
        diff_count = 0
        home_goals_count = 0
        away_goals_count = 0
        total_points = 0
        bonus_used = 0
        bonus_points = 0
        near_exact_count = 0
        best_prediction = None
        worst_prediction = None
        streak = 0
        best_streak = 0
        effectiveness = cls._empty_outcome_effectiveness()

        for match in matches:
            prediction = predictions_by_match.get(match.id)
            if not prediction:
                continue

            breakdown = cls._get_breakdown(prediction)
            prediction_points = cls._get_prediction_points(prediction)
            total_points += prediction_points

            exact_count += int(cls._has_breakdown_key(breakdown, "exact_score"))
            outcome_hit = cls._has_breakdown_key(breakdown, "home_or_away_winner")
            outcome_count += int(outcome_hit)
            diff_count += int(cls._has_breakdown_key(breakdown, "diff_correct_outcome"))
            home_goals_count += int(cls._has_breakdown_key(breakdown, "home_correct_outcome"))
            away_goals_count += int(cls._has_breakdown_key(breakdown, "away_correct_outcome"))
            bonus_used += int(prediction.is_doubled)
            bonus_points += cls._get_bonus_points(breakdown)
            near_exact_count += int(cls._is_near_exact(match, prediction, breakdown))

            outcome_key = cls._get_actual_outcome(match)
            if outcome_key:
                effectiveness[outcome_key]["total"] += 1
                effectiveness[outcome_key]["correct"] += int(outcome_hit)

            if outcome_hit:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0

            best_prediction = cls._pick_better_prediction(best_prediction, prediction, higher=True)
            worst_prediction = cls._pick_better_prediction(worst_prediction, prediction, higher=False)

        for item in effectiveness.values():
            item["percent"] = cls._percentage(item["correct"], item["total"])

        ranking = cls.get_round_ranking(stage)
        rank = cls._get_rank_for_user(ranking, user)

        return {
            "stage": stage,
            "total_matches": total_matches,
            "predicted_matches": predicted_count,
            "prediction_percent": cls._percentage(predicted_count, total_matches),
            "missing_matches": missing_count,
            "exact_scores": exact_count,
            "exact_percent": cls._percentage(exact_count, predicted_count),
            "correct_outcomes": outcome_count,
            "outcome_percent": cls._percentage(outcome_count, predicted_count),
            "correct_diffs": diff_count,
            "correct_home_goals": home_goals_count,
            "correct_away_goals": away_goals_count,
            "total_points": total_points,
            "average_points": cls._rounded_ratio(total_points, predicted_count),
            "best_prediction": cls._format_prediction(best_prediction, country_language),
            "worst_prediction": cls._format_prediction(worst_prediction, country_language),
            "rank": rank,
            "rank_change": cls._get_rank_change(user, stage, rank),
            "bonus_used": bonus_used,
            "bonus_points": bonus_points,
            "outcome_effectiveness": effectiveness,
            "longest_outcome_streak": best_streak,
            "near_exact_matches": near_exact_count,
            "message": "" if predicted_count else "Nie obstawiłeś żadnego meczu w tej rundzie.",
        }

    @classmethod
    def get_global_stats(cls, stage, country_language="pl"):
        matches = cls._get_stage_matches(stage)
        predictions = cls._get_stage_predictions(stage)
        total_matches = len(matches)
        participants = {
            prediction.user_id
            for prediction in predictions
        }
        participant_count = len(participants)
        prediction_count = len(predictions)
        total_possible_predictions = participant_count * total_matches
        total_points = sum(cls._get_prediction_points(prediction) for prediction in predictions)
        exact_count = sum(
            int(cls._has_breakdown_key(cls._get_breakdown(prediction), "exact_score"))
            for prediction in predictions
        )
        outcome_count = sum(
            int(cls._has_breakdown_key(cls._get_breakdown(prediction), "home_or_away_winner"))
            for prediction in predictions
        )
        bonus_used = sum(int(prediction.is_doubled) for prediction in predictions)
        bonus_points = sum(cls._get_bonus_points(cls._get_breakdown(prediction)) for prediction in predictions)
        ranking = cls.get_round_ranking(stage)
        match_stats = cls._get_match_stats(matches, predictions, country_language)

        return {
            "stage": stage,
            "participant_count": participant_count,
            "prediction_count": prediction_count,
            "average_predictions_per_user": cls._rounded_ratio(prediction_count, participant_count),
            "global_prediction_percent": cls._percentage(prediction_count, total_possible_predictions),
            "exact_scores": exact_count,
            "exact_percent": cls._percentage(exact_count, prediction_count),
            "correct_outcomes": outcome_count,
            "outcome_percent": cls._percentage(outcome_count, prediction_count),
            "average_points_per_user": cls._rounded_ratio(total_points, participant_count),
            "average_points_per_prediction": cls._rounded_ratio(total_points, prediction_count),
            "best_user": ranking[0] if ranking else None,
            "top_three": ranking[:3],
            "most_exact_user": cls._pick_ranking_leader(ranking, "exact_scores"),
            "best_effectiveness_user": cls._pick_best_effectiveness_user(ranking, total_matches),
            "easiest_match": cls._pick_match_stat(match_stats, "outcome_percent", higher=True),
            "hardest_match": cls._pick_match_stat(match_stats, "outcome_percent", higher=False),
            "most_exact_match": cls._pick_match_stat(match_stats, "exact_scores", higher=True),
            "most_points_match": cls._pick_match_stat(match_stats, "total_points", higher=True),
            "bonus_used": bonus_used,
            "bonus_points": bonus_points,
            "ranking": ranking,
            "match_stats": match_stats,
            "total_points": total_points,
        }

    @classmethod
    def get_round_ranking(cls, stage):
        matches = cls._get_stage_matches(stage)
        total_matches = len(matches)
        predictions = cls._get_stage_predictions(stage)
        grouped = defaultdict(list)

        for prediction in predictions:
            grouped[prediction.user_id].append(prediction)

        users_by_id = {
            user.id: user
            for user in User.objects.filter(id__in=grouped.keys())
        }
        ranking = []

        for user_id, user_predictions in grouped.items():
            total_points = sum(cls._get_prediction_points(prediction) for prediction in user_predictions)
            exact_scores = sum(
                int(cls._has_breakdown_key(cls._get_breakdown(prediction), "exact_score"))
                for prediction in user_predictions
            )
            correct_outcomes = sum(
                int(cls._has_breakdown_key(cls._get_breakdown(prediction), "home_or_away_winner"))
                for prediction in user_predictions
            )
            ranking.append({
                "user": users_by_id[user_id],
                "points": total_points,
                "predicted_matches": len(user_predictions),
                "exact_scores": exact_scores,
                "correct_outcomes": correct_outcomes,
                "outcome_percent": cls._percentage(correct_outcomes, len(user_predictions)),
                "prediction_percent": cls._percentage(len(user_predictions), total_matches),
            })

        ranking.sort(
            key=lambda row: (
                -row["points"],
                -row["exact_scores"],
                row["user"].username.lower(),
            )
        )

        for index, row in enumerate(ranking, start=1):
            row["rank"] = index

        return ranking

    @classmethod
    def get_user_round_history(cls, user, country_language="pl"):
        history = []

        for stage in cls.get_finished_stages():
            user_stats = cls.get_user_stats(user, stage, country_language)
            last_match = Match.objects.filter(stage=stage).order_by("-kickoff").first()
            history.append({
                "stage": stage,
                "points": user_stats["total_points"],
                "rank": user_stats["rank"],
                "exact_scores": user_stats["exact_scores"],
                "outcome_percent": user_stats["outcome_percent"],
                "predicted_matches": user_stats["predicted_matches"],
                "total_matches": user_stats["total_matches"],
                "finished_at": last_match.kickoff if last_match else None,
            })

        return history

    @classmethod
    def get_stats_context(cls, user, stage=None, country_language="pl"):
        finished_stages = cls.get_finished_stages()
        selected_stage = stage if stage in finished_stages else cls.get_latest_completed_stage()

        if not selected_stage:
            return {
                "has_finished_stage": False,
                "finished_stages": [],
                "selected_stage": None,
                "user_stats": None,
                "global_stats": None,
                "round_history": [],
            }

        return {
            "has_finished_stage": True,
            "finished_stages": finished_stages,
            "selected_stage": selected_stage,
            "user_stats": cls.get_user_stats(user, selected_stage, country_language),
            "global_stats": cls.get_global_stats(selected_stage, country_language),
            "round_history": cls.get_user_round_history(user, country_language),
        }

    @classmethod
    def get_home_summary(cls, user, country_language="pl"):
        if not user or not user.is_authenticated:
            return None

        stage = cls.get_latest_completed_stage()
        if not stage:
            return None

        user_stats = cls.get_user_stats(user, stage, country_language)
        global_stats = cls.get_global_stats(stage, country_language)
        return {
            "stage": stage,
            "user_points": user_stats["total_points"],
            "user_rank": user_stats["rank"],
            "exact_scores": user_stats["exact_scores"],
            "outcome_percent": user_stats["outcome_percent"],
            "best_prediction": user_stats["best_prediction"],
            "winner": global_stats["best_user"],
            "average_points": global_stats["average_points_per_user"],
        }

    @classmethod
    def _get_stage_matches(cls, stage):
        return list(
            Match.objects.select_related("home_team", "away_team")
            .filter(stage=stage)
            .order_by("kickoff", "id")
        )

    @classmethod
    def _get_stage_predictions(cls, stage):
        return list(
            Prediction.objects.select_related(
                "user",
                "match",
                "match__home_team",
                "match__away_team",
            )
            .filter(match__stage=stage)
            .order_by("match__kickoff", "id")
        )

    @classmethod
    def _get_user_predictions(cls, user, stage):
        return [
            prediction
            for prediction in cls._get_stage_predictions(stage)
            if prediction.user_id == user.id
        ]

    @staticmethod
    def _match_is_finished(match):
        return (
            match.status == "FINISHED"
            and match.home_score is not None
            and match.away_score is not None
        )

    @staticmethod
    def _percentage(value, total):
        if not total:
            return 0.0
        return round((value / total) * 100, 1)

    @staticmethod
    def _rounded_ratio(value, total):
        if not total:
            return 0.0
        return round(value / total, 1)

    @staticmethod
    def _get_breakdown(prediction):
        if hasattr(prediction, "_stats_breakdown"):
            return prediction._stats_breakdown

        if prediction.points_breakdown is not None:
            prediction._stats_breakdown = prediction.points_breakdown or {}
            prediction._stats_points = prediction.points
            return prediction._stats_breakdown

        points, breakdown = ScoringService.calculate_points(prediction.match, prediction)
        prediction._stats_points = points
        prediction._stats_breakdown = breakdown
        return prediction._stats_breakdown

    @staticmethod
    def _get_prediction_points(prediction):
        if hasattr(prediction, "_stats_points"):
            return prediction._stats_points

        if prediction.points_breakdown is not None:
            prediction._stats_breakdown = prediction.points_breakdown or {}
            prediction._stats_points = prediction.points
            return prediction.points

        points, breakdown = ScoringService.calculate_points(prediction.match, prediction)
        prediction._stats_points = points
        prediction._stats_breakdown = breakdown
        return prediction._stats_points

    @staticmethod
    def _has_breakdown_key(breakdown, key):
        return key in (breakdown or {})

    @staticmethod
    def _get_bonus_points(breakdown):
        return (breakdown or {}).get("bonus", {}).get("points", 0)

    @staticmethod
    def _get_actual_outcome(match):
        if match.home_score is None or match.away_score is None:
            return None
        if match.home_score > match.away_score:
            return "home"
        if match.away_score > match.home_score:
            return "away"
        return "draw"

    @staticmethod
    def _get_predicted_outcome(prediction):
        if prediction.predicted_home > prediction.predicted_away:
            return "home"
        if prediction.predicted_away > prediction.predicted_home:
            return "away"
        return "draw"

    @staticmethod
    def _empty_outcome_effectiveness():
        return {
            "home": {"label": "Wygrane gospodarzy", "total": 0, "correct": 0, "percent": 0.0},
            "draw": {"label": "Remisy", "total": 0, "correct": 0, "percent": 0.0},
            "away": {"label": "Wygrane gości", "total": 0, "correct": 0, "percent": 0.0},
        }

    @classmethod
    def _is_near_exact(cls, match, prediction, breakdown):
        if cls._has_breakdown_key(breakdown, "exact_score"):
            return False

        total_miss = (
            abs(match.home_score - prediction.predicted_home)
            + abs(match.away_score - prediction.predicted_away)
        )
        return total_miss == 1

    @staticmethod
    def _pick_better_prediction(current, candidate, higher):
        if current is None:
            return candidate

        if higher:
            return candidate if candidate.points > current.points else current
        return candidate if candidate.points < current.points else current

    @classmethod
    def _format_prediction(cls, prediction, country_language="pl"):
        if not prediction:
            return None

        match = prediction.match
        return {
            "match": match,
            "label": cls._format_match_label(match, country_language),
            "predicted_score": f"{prediction.predicted_home}:{prediction.predicted_away}",
            "actual_score": f"{match.home_score}:{match.away_score}",
            "points": prediction.points,
        }

    @classmethod
    def _get_rank_for_user(cls, ranking, user):
        for row in ranking:
            if row["user"].id == user.id:
                return row["rank"]
        return None

    @classmethod
    def _get_rank_change(cls, user, stage, current_rank):
        if current_rank is None:
            return None

        stages = cls.get_finished_stages()
        if stage not in stages:
            return None

        stage_index = stages.index(stage)
        if stage_index == 0:
            return None

        previous_stage = stages[stage_index - 1]
        previous_rank = cls._get_rank_for_user(cls.get_round_ranking(previous_stage), user)
        if previous_rank is None:
            return None

        return previous_rank - current_rank

    @classmethod
    def _get_match_stats(cls, matches, predictions, country_language="pl"):
        predictions_by_match = defaultdict(list)
        for prediction in predictions:
            predictions_by_match[prediction.match_id].append(prediction)

        stats = []
        for match in matches:
            match_predictions = predictions_by_match.get(match.id, [])
            exact_scores = 0
            correct_outcomes = 0
            total_points = 0

            for prediction in match_predictions:
                breakdown = cls._get_breakdown(prediction)
                exact_scores += int(cls._has_breakdown_key(breakdown, "exact_score"))
                correct_outcomes += int(cls._has_breakdown_key(breakdown, "home_or_away_winner"))
                total_points += cls._get_prediction_points(prediction)

            stats.append({
                "match": match,
                "label": cls._format_match_label(match, country_language),
                "prediction_count": len(match_predictions),
                "exact_scores": exact_scores,
                "correct_outcomes": correct_outcomes,
                "outcome_percent": cls._percentage(correct_outcomes, len(match_predictions)),
                "total_points": total_points,
            })

        return stats

    @staticmethod
    def _format_match_label(match, country_language="pl"):
        home_name = TeamNameService.get_team_name(match.home_team, country_language)
        away_name = TeamNameService.get_team_name(match.away_team, country_language)
        return f"{home_name} vs {away_name}"

    @staticmethod
    def _pick_match_stat(match_stats, key, higher):
        available = [
            stat
            for stat in match_stats
            if stat["prediction_count"] > 0
        ]
        if not available:
            return None

        return sorted(
            available,
            key=lambda stat: stat[key],
            reverse=higher,
        )[0]

    @staticmethod
    def _pick_ranking_leader(ranking, key):
        if not ranking:
            return None
        return sorted(ranking, key=lambda row: (-row[key], row["user"].username.lower()))[0]

    @classmethod
    def _pick_best_effectiveness_user(cls, ranking, total_matches):
        minimum_predictions = max(int(total_matches * cls.MIN_EFFECTIVENESS_RATIO), 1)
        candidates = [
            row
            for row in ranking
            if row["predicted_matches"] >= minimum_predictions
        ]
        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda row: (-row["outcome_percent"], -row["points"], row["user"].username.lower()),
        )[0]
