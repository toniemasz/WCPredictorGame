from tournament.models import Match, Prediction


class AchievementService:
    ACHIEVEMENTS = (
        {
            "slug": "perfect_pick",
            "emoji": "🎯",
            "title": "Doskonały typ!",
            "description": "Traf dokładny wynik, rozstrzygnięcie, gole obu drużyn, pierwszą drużynę z golem i pierwszego strzelca.",
            "checker": "_has_perfect_pick",
        },
        {
            "slug": "good_scorer",
            "emoji": "⚽",
            "title": "Dobry strzelec!",
            "description": "Traf pierwszego strzelca bramki.",
            "checker": "_has_first_scorer_hit",
        },
        {
            "slug": "zero_points",
            "emoji": "🫠",
            "title": "Przegryw!",
            "description": "Zdobądź 0 punktów za zakończony mecz.",
            "checker": "_has_zero_point_match",
        },
        {
            "slug": "ten_predictions",
            "emoji": "🔟",
            "title": "Obstawiłeś 10 meczów!",
            "description": "Zapisz typy dla 10 meczów.",
            "checker": "_has_ten_predictions",
        },
        {
            "slug": "fifty_predictions",
            "emoji": "🏟️",
            "title": "Obstawiłeś 50 meczów!",
            "description": "Zapisz typy dla 50 meczów.",
            "checker": "_has_fifty_predictions",
        },
        {
            "slug": "all_matches",
            "emoji": "🌍",
            "title": "Cały mundial obstawiony!",
            "description": "Obstaw wszystkie mecze zapisane w terminarzu mundialu.",
            "checker": "_has_all_matches_predicted",
        },
        {
            "slug": "first_points",
            "emoji": "✨",
            "title": "Pierwsze punkty!",
            "description": "Zdobądź pierwsze punkty za dowolny mecz.",
            "checker": "_has_first_points",
        },
        {
            "slug": "exact_score",
            "emoji": "🥅",
            "title": "W punkt!",
            "description": "Traf dokładny wynik meczu.",
            "checker": "_has_exact_score",
        },
        {
            "slug": "draw_master",
            "emoji": "🤝",
            "title": "Mistrz remisów",
            "description": "Poprawnie przewidź remis.",
            "checker": "_has_correct_draw",
        },
        {
            "slug": "bonus_profit",
            "emoji": "🔥",
            "title": "Podwójna zdobycz",
            "description": "Zdobądź punkty w meczu z aktywnym bonusem x2.",
            "checker": "_has_scored_double_bonus",
        },
        {
            "slug": "difference_hit",
            "emoji": "📐",
            "title": "Król różnicy",
            "description": "Traf poprawną różnicę bramek.",
            "checker": "_has_goal_difference_hit",
        },
    )

    @classmethod
    def get_user_achievements(cls, user):
        context = cls._build_user_context(user)
        achievements = []

        for definition in cls.ACHIEVEMENTS:
            checker = getattr(cls, definition["checker"])
            achievements.append({
                **definition,
                "unlocked": checker(context),
            })

        return achievements

    @classmethod
    def get_user_summary(cls, user):
        achievements = cls.get_user_achievements(user)
        unlocked_count = sum(1 for achievement in achievements if achievement["unlocked"])
        total_count = len(achievements)
        return {
            "achievements": achievements,
            "unlocked_count": unlocked_count,
            "total_count": total_count,
            "locked_count": total_count - unlocked_count,
        }

    @classmethod
    def get_page_context(cls, user):
        summary = cls.get_user_summary(user)
        return {
            **summary,
            "target_user": user,
        }

    @classmethod
    def _build_user_context(cls, user):
        predictions = list(
            Prediction.objects.select_related("match")
            .filter(user=user)
            .order_by("match__kickoff", "id")
        )
        total_matches = Match.objects.count()
        predicted_match_count = (
            Prediction.objects.filter(user=user)
            .values("match_id")
            .distinct()
            .count()
        )
        return {
            "predictions": predictions,
            "total_matches": total_matches,
            "predicted_match_count": predicted_match_count,
        }

    @staticmethod
    def _breakdown(prediction):
        return prediction.points_breakdown or {}

    @classmethod
    def _has_breakdown_key(cls, prediction, key):
        return key in cls._breakdown(prediction)

    @classmethod
    def _has_perfect_pick(cls, context):
        required_keys = {
            "exact_score",
            "diff_correct_outcome",
            "home_correct_outcome",
            "away_correct_outcome",
            "home_or_away_winner",
            "first_team",
            "first_scorer",
        }
        return any(
            required_keys.issubset(cls._breakdown(prediction))
            for prediction in context["predictions"]
        )

    @classmethod
    def _has_first_scorer_hit(cls, context):
        return any(
            cls._has_breakdown_key(prediction, "first_scorer")
            for prediction in context["predictions"]
        )

    @staticmethod
    def _has_zero_point_match(context):
        return any(
            prediction.match.status == "FINISHED" and prediction.points == 0
            for prediction in context["predictions"]
        )

    @staticmethod
    def _has_ten_predictions(context):
        return context["predicted_match_count"] >= 10

    @staticmethod
    def _has_fifty_predictions(context):
        return context["predicted_match_count"] >= 50

    @staticmethod
    def _has_all_matches_predicted(context):
        return (
            context["total_matches"] > 0
            and context["predicted_match_count"] >= context["total_matches"]
        )

    @staticmethod
    def _has_first_points(context):
        return any(prediction.points > 0 for prediction in context["predictions"])

    @classmethod
    def _has_exact_score(cls, context):
        return any(
            cls._has_breakdown_key(prediction, "exact_score")
            for prediction in context["predictions"]
        )

    @classmethod
    def _has_correct_draw(cls, context):
        return any(
            prediction.match.home_score == prediction.match.away_score
            and cls._has_breakdown_key(prediction, "home_or_away_winner")
            for prediction in context["predictions"]
            if prediction.match.home_score is not None and prediction.match.away_score is not None
        )

    @classmethod
    def _has_scored_double_bonus(cls, context):
        return any(
            prediction.is_doubled
            and cls._has_breakdown_key(prediction, "bonus")
            for prediction in context["predictions"]
        )

    @classmethod
    def _has_goal_difference_hit(cls, context):
        return any(
            cls._has_breakdown_key(prediction, "diff_correct_outcome")
            for prediction in context["predictions"]
        )
