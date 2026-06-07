from tournament.models import Match, Prediction


class ScoringService:

    @classmethod
    def calculate_points_for_match(cls, match: Match):
        if match.home_score is None or match.away_score is None:
            return

        predictions = Prediction.objects.filter(match=match)
        users_to_update = []

        # Przygotowanie listy rzeczywistych strzelców (ignoruje wielkość liter i spacje)
        actual_scorers = []
        if match.goalscorers:
            actual_scorers = [s.strip().lower() for s in match.goalscorers.split(',') if s.strip()]

        for prediction in predictions:
            points = cls._calculate_single_prediction(
                actual_home=match.home_score,
                actual_away=match.away_score,
                pred_home=prediction.predicted_home,
                pred_away=prediction.predicted_away,
                is_doubled=prediction.is_doubled,
                actual_first_team=match.first_scoring_team,
                pred_first_team=prediction.predicted_first_team,
                actual_scorers=actual_scorers,
                pred_scorer=prediction.predicted_scorer,
                home_odds=match.home_odds,
                draw_odds=match.draw_odds,
                away_odds=match.away_odds
            )

            if prediction.points != points:
                prediction.points = points
                prediction.save(update_fields=['points'])
                users_to_update.append(prediction.user)

        for user in set(users_to_update):
            user.profile.update_total_points()

    @staticmethod
    def _calculate_single_prediction(actual_home, actual_away, pred_home, pred_away, is_doubled,
                                     actual_first_team, pred_first_team,
                                     actual_scorers, pred_scorer,
                                     home_odds, draw_odds, away_odds):
        points = 0
        is_exact_score = False
        is_correct_first_team = False
        is_correct_scorer = False
        is_correct_winner = False

        # --- 1. WYNIK MECZU ---
        actual_diff = actual_home - actual_away
        pred_diff = pred_home - pred_away

        # Trafiony zwycięzca / remis (+3 pkt)
        if (actual_diff > 0 and pred_diff > 0) or \
                (actual_diff < 0 and pred_diff < 0) or \
                (actual_diff == 0 and pred_diff == 0):
            points += 3
            is_correct_winner = True

        # Trafiona liczba bramek gospodarzy (+2 pkt)
        if actual_home == pred_home:
            points += 2

        # Trafiona liczba bramek gości (+2 pkt)
        if actual_away == pred_away:
            points += 2

        # Trafiona różnica bramek (+3 pkt)
        if actual_diff == pred_diff:
            points += 3

        # Bonus za dokładny wynik (+5 pkt)
        if actual_home == pred_home and actual_away == pred_away:
            points += 5
            is_exact_score = True

        # --- 2. PIERWSZA DRUŻYNA STRZELAJĄCA ---
        if (actual_home + actual_away) > 0 and actual_first_team:
            if pred_first_team and actual_first_team == pred_first_team:
                points += 2
                is_correct_first_team = True

        # --- 3. STRZELEC GOLA ---
        if pred_scorer and pred_scorer.strip().lower() in actual_scorers:
            points += 3
            is_correct_scorer = True

        if is_correct_winner:
            odds = 0
            if actual_diff > 0 and home_odds:
                odds = float(home_odds)
            elif actual_diff < 0 and away_odds:
                odds = float(away_odds)
            elif actual_diff == 0 and draw_odds:
                odds = float(draw_odds)

            if odds:
                if 1.81 <= odds <= 2.50:
                    points += 1
                elif 2.51 <= odds <= 3.50:
                    points += 2
                elif odds > 3.50:
                    points += 3

        # --- 5. BONUS ZA PERFEKCYJNY MECZ ---
        if is_exact_score and is_correct_first_team and is_correct_scorer:
            points += 5

        # --- 6. BONUS x2 (Joker) ---
        if is_doubled:
            points *= 2

        return points