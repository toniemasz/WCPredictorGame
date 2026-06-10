# tournament/services/scoring_service.py
import math

correct_result_points = 5
correct_home_or_away_goals_points = 3
correct_goal_diff_points = 3
correct_home_or_away_win_points = 2
correct_first_scorer_points = 10
correct_first_team_scored = 5

class ScoringService:
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
            f"• Bonus x2: podwaja całkowitą sumę punktów. (limit 2 na rundę)"
            f"• Bonus za underdoga: Czym wyższy kurs tym więcej bonusu jeżeli drużyna wygra"
        )



    @staticmethod
    def calculate_points(match, prediction):
        # 1. Zabezpieczenie: Liczymy punkty tylko gdy admin wpisał jakikolwiek wynik (nawet LIVE)
        if match.home_score is None or match.away_score is None:
            return 0, {}

        points = 0
        breakdown = {}
        pred_diff = prediction.predicted_home - prediction.predicted_away
        actual_diff = match.home_score - match.away_score
        actual_first_team = match.first_scoring_team
        pred_first_team = prediction.predicted_first_team
        actual_scorer = (match.first_scorer or "").strip().lower()
        pred_scorer = (prediction.predicted_scorer or "").strip().lower()

        odd_home = match.home_odds
        odd_away = match.away_odds
        odd_draw = match.draw_odds

        home_winner = match.home_score > match.away_score
        away_winner = match.away_score > match.home_score
        draw = match.home_score == match.away_score

        pred_home_winner = prediction.predicted_home > prediction.predicted_away
        pred_away_winner = prediction.predicted_away > prediction.predicted_home
        pred_draw = prediction.predicted_home == prediction.predicted_away


        if prediction.predicted_home is not None and prediction.predicted_away is not None:
            if prediction.predicted_home == match.home_score and prediction.predicted_away == match.away_score:
                points += correct_result_points
                breakdown['exact_score'] = {"name": "Dokładny wynik", "points": correct_result_points}

                #Różnica goli poprawna

            if pred_diff == actual_diff:
                points += correct_goal_diff_points
                breakdown['diff_correct_outcome'] = {"name": "Poprawna różnica bramek", "points": correct_goal_diff_points}
            #Home dobrze
            if prediction.predicted_home == match.home_score and prediction.predicted_away != match.away_score:
                points += correct_home_or_away_goals_points
                breakdown['home_correct_outcome'] = {"name": "Poprawna ilość bramek dla Gospodarzy", "points": correct_home_or_away_goals_points}
            # AWAY dobrze
            if prediction.predicted_home != match.home_score and prediction.predicted_away == match.away_score:
                points += correct_home_or_away_goals_points
                breakdown['away_correct_outcome'] = {"name": "Poprawna ilość bramek dla Gości", "points": correct_home_or_away_goals_points}
            if (home_winner and pred_home_winner) or (away_winner and pred_away_winner) or (draw and pred_draw):
                points += correct_home_or_away_win_points
                breakdown['home_or_away_winner'] = {"name": "Poprawna wygrana", "points": correct_home_or_away_win_points}


        if pred_first_team and actual_first_team:
            if prediction.predicted_first_team == actual_first_team:
                points += correct_first_team_scored
                breakdown['first_team'] = {"name": "Poprawna drużyna która strzeliła gola jako pierwsza", "points": correct_first_team_scored}

        if pred_scorer and actual_scorer:
            if pred_scorer == actual_scorer:
                points += correct_first_scorer_points
                breakdown['first_scorer'] = {"name": "Trafiony strzelec 1 bramki", "points": correct_first_scorer_points}

        if odd_home and odd_away and odd_draw:

            if odd_home < 3:
                odd_home_bonus = 0
            else:
                odd_home_bonus = round(math.log(odd_home / 3) * 10)

            if odd_away < 3:
                odd_away_bonus = 0
            else:
                odd_away_bonus = round(math.log(odd_away / 3) * 10)

            if odd_draw:
                if odd_draw < 3:
                    odd_draw_bonus = 0
                else:
                    odd_draw_bonus = round(math.log(float(odd_draw) / 3) * 10)

                if draw and pred_draw and odd_draw_bonus > 0:
                    points += odd_draw_bonus
                    breakdown['underdog_bonus_draw'] = {
                        "name": "Bonus za trafiony remis",
                        "points": odd_draw_bonus
                    }
            if home_winner and pred_home_winner and odd_home_bonus > 0:
                points += odd_home_bonus
                breakdown['underdog_bonus_home'] = {"name": "Bonus za underdoga",
                                           "points": odd_home_bonus}
            if away_winner and pred_away_winner and odd_away_bonus > 0:
                points += odd_away_bonus
                breakdown['underdog_bonus_away'] = {"name": "Bonus za underdoga",
                                           "points": odd_away_bonus}


        if prediction.is_doubled and points > 0:
            base_points = points  # zapisujemy, ile punktów dał nam mnożnik
            points *= 2
            breakdown['bonus'] = {"name": "Bonus x2 (Mnożnik)", "points": base_points}

        return points, breakdown

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
