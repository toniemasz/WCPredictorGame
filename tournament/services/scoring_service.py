# tournament/services/scoring_service.py
import math

correct_result_points = 3
correct_home_or_away_goals_points = 3
correct_goal_diff_points = 2
correct_home_or_away_win_points = 3
correct_first_scorer_points = 10
correct_first_team_scored = 2

class ScoringService:
    NO_SCORER = "NO_SCORER"
    NO_SCORER_LABEL = "Brak strzelca"

    @staticmethod
    def get_rules_explanation():
        return (
            f"Zasady punktacji:\n"
            f"• Dokładny wynik bramkowy: +{correct_result_points} punkty\n"
            f"• Poprawny wynik gospodarzy/gości: +{correct_home_or_away_goals_points} punkt\n"
            f"• Poprawna wygrana gospodarzy/gości: +{correct_home_or_away_win_points} punkt\n"
            f"• Poprawna różnica bramek: +{correct_goal_diff_points} punkt\n"
            f"• Poprawny pierwszy strzelec: +{correct_first_scorer_points} punkty\n"
            f"• Poprawna pierwsza bramka drużyny: +{correct_first_team_scored} punkty\n"
            f"• Bonus x2: podwaja całkowitą sumę punktów. (limit 2 na rundę)\n"
            f"• Bonus za underdoga: Czym wyższy kurs tym więcej bonusu jeżeli drużyna wygra"
        )



    @classmethod
    def calculate_points(cls, match, prediction):
        if cls._match_has_no_result(match):
            return 0, {}

        points = 0
        breakdown = {}

        points = cls._add_score_points(match, prediction, points, breakdown)
        points = cls._add_first_goal_points(match, prediction, points, breakdown)
        points = cls._add_underdog_points(match, prediction, points, breakdown)
        points = cls._apply_double_bonus(prediction, points, breakdown)

        return points, breakdown

    @staticmethod
    def _match_has_no_result(match):
        return match.home_score is None or match.away_score is None

    @classmethod
    def _add_score_points(cls, match, prediction, points, breakdown):
        pred_diff = abs(prediction.predicted_home - prediction.predicted_away)
        actual_diff = abs(match.home_score - match.away_score)
        home_winner = match.home_score > match.away_score
        away_winner = match.away_score > match.home_score
        draw = match.home_score == match.away_score
        pred_home_winner = prediction.predicted_home > prediction.predicted_away
        pred_away_winner = prediction.predicted_away > prediction.predicted_home
        pred_draw = prediction.predicted_home == prediction.predicted_away

        if prediction.predicted_home is not None and prediction.predicted_away is not None:
            if prediction.predicted_home == match.home_score and prediction.predicted_away == match.away_score:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'exact_score',
                    "Dokładny wynik",
                    correct_result_points,
                )

            if pred_diff == actual_diff:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'diff_correct_outcome',
                    "Poprawna różnica bramek",
                    correct_goal_diff_points,
                )

            if prediction.predicted_home == match.home_score:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'home_correct_outcome',
                    "Poprawna ilość bramek dla Gospodarzy",
                    correct_home_or_away_goals_points,
                )

            if prediction.predicted_away == match.away_score:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'away_correct_outcome',
                    "Poprawna ilość bramek dla Gości",
                    correct_home_or_away_goals_points,
                )

            if (home_winner and pred_home_winner) or (away_winner and pred_away_winner) or (draw and pred_draw):
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'home_or_away_winner',
                    "Poprawna wygrana",
                    correct_home_or_away_win_points,
                )

        return points

    @classmethod
    def _add_first_goal_points(cls, match, prediction, points, breakdown):
        actual_first_team = match.first_scoring_team
        pred_first_team = prediction.predicted_first_team
        actual_scorer = cls._normalize_actual_scorer(match)
        pred_scorer = cls.normalize_scorer(prediction.predicted_scorer)

        if pred_first_team and actual_first_team:
            if prediction.predicted_first_team == actual_first_team:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'first_team',
                    "Poprawna drużyna która strzeliła gola jako pierwsza",
                    correct_first_team_scored,
                )

        if pred_scorer and actual_scorer:
            if pred_scorer == actual_scorer:
                points = cls._add_breakdown(
                    points,
                    breakdown,
                    'first_scorer',
                    "Trafiony strzelec 1 bramki",
                    correct_first_scorer_points,
                )

        return points

    @classmethod
    def normalize_scorer(cls, scorer):
        scorer = (scorer or "").strip()
        if not scorer:
            return ""

        if scorer == cls.NO_SCORER or scorer.lower() in {"brak strzelca", "no scorer"}:
            return cls.NO_SCORER

        return scorer.lower()

    @classmethod
    def _normalize_actual_scorer(cls, match):
        if match.first_scoring_team == "NONE":
            return cls.NO_SCORER

        return cls.normalize_scorer(match.first_scorer)

    @classmethod
    def get_scorer_label(cls, scorer, empty_label="-"):
        if cls.normalize_scorer(scorer) == cls.NO_SCORER:
            return cls.NO_SCORER_LABEL

        return (scorer or "").strip() or empty_label

    @classmethod
    def get_actual_scorer_label(cls, match, empty_label="-"):
        if cls._normalize_actual_scorer(match) == cls.NO_SCORER:
            return cls.NO_SCORER_LABEL

        return cls.get_scorer_label(match.first_scorer, empty_label)

    @classmethod
    def scorers_match(cls, predicted_scorer, match):
        pred_scorer = cls.normalize_scorer(predicted_scorer)
        actual_scorer = cls._normalize_actual_scorer(match)
        return bool(pred_scorer and actual_scorer and pred_scorer == actual_scorer)

    @classmethod
    def _add_underdog_points(cls, match, prediction, points, breakdown):
        odd_home = match.home_odds
        odd_away = match.away_odds
        odd_draw = match.draw_odds

        if not (odd_home and odd_away and odd_draw):
            return points

        odd_home_bonus = cls._calculate_underdog_bonus(odd_home)
        odd_away_bonus = cls._calculate_underdog_bonus(odd_away)
        odd_draw_bonus = cls._calculate_underdog_bonus(odd_draw)

        home_winner = match.home_score > match.away_score
        away_winner = match.away_score > match.home_score
        draw = match.home_score == match.away_score
        pred_home_winner = prediction.predicted_home > prediction.predicted_away
        pred_away_winner = prediction.predicted_away > prediction.predicted_home
        pred_draw = prediction.predicted_home == prediction.predicted_away

        if draw and pred_draw and odd_draw_bonus > 0:
            points = cls._add_breakdown(
                points,
                breakdown,
                'underdog_bonus_draw',
                "Bonus za trafiony remis",
                odd_draw_bonus,
            )

        if home_winner and pred_home_winner and odd_home_bonus > 0:
            points = cls._add_breakdown(
                points,
                breakdown,
                'underdog_bonus_home',
                "Bonus za underdoga",
                odd_home_bonus,
            )

        if away_winner and pred_away_winner and odd_away_bonus > 0:
            points = cls._add_breakdown(
                points,
                breakdown,
                'underdog_bonus_away',
                "Bonus za underdoga",
                odd_away_bonus,
            )

        return points

    @staticmethod
    def _calculate_underdog_bonus(odd):
        if odd < 3:
            return 0

        return round(math.log(float(odd) / 3) * 10)

    @classmethod
    def _apply_double_bonus(cls, prediction, points, breakdown):
        if prediction.is_doubled and points > 0:
            base_points = points
            points *= 2
            breakdown['bonus'] = {"name": "Bonus x2 (Mnożnik)", "points": base_points}

        return points

    @staticmethod
    def _add_breakdown(points, breakdown, key, name, awarded_points):
        points += awarded_points
        breakdown[key] = {"name": name, "points": awarded_points}
        return points

    @classmethod
    def recalculate_match(cls, match):
        predictions = match.prediction_set.all()

        for pred in predictions:
            total_points, breakdown = cls.calculate_points(match, pred)

            if pred.points != total_points or pred.points_breakdown != breakdown:
                pred.points = total_points
                pred.points_breakdown = breakdown
                pred.save(update_fields=['points', 'points_breakdown'])

    @classmethod
    def recalculate_finished_matches(cls):
        from tournament.models import Match

        matches = Match.objects.filter(status__in=['LIVE', 'FINISHED'])

        for match in matches:
            cls.recalculate_match(match)

        return matches.count()
