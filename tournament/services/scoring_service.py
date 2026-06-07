# tournament/services/scoring_service.py
from tournament.models import Match, Prediction


class ScoringService:

    @classmethod
    def calculate_points_for_match(cls, match: Match):
        """
        Przelicza punkty dla wszystkich przewidywań związanych z danym meczem.
        Jeżeli mecz trwa (LIVE) lub się skończył (FINISHED) i ma wyniki.
        """
        if match.home_score is None or match.away_score is None:
            return  # Nie ma jeszcze wyniku do przeliczenia

        predictions = Prediction.objects.filter(match=match)
        users_to_update = []

        for prediction in predictions:
            points = cls._calculate_single_prediction(
                actual_home=match.home_score,
                actual_away=match.away_score,
                pred_home=prediction.predicted_home,
                pred_away=prediction.predicted_away,
                is_doubled=prediction.is_doubled
            )

            # Aktualizujemy punkty przewidywania tylko jeśli się zmieniły
            if prediction.points != points:
                prediction.points = points
                prediction.save(update_fields=['points'])
                users_to_update.append(prediction.user)

        # Na koniec aktualizujemy łączne punkty na profilach graczy
        for user in set(users_to_update):  # set aby uniknąć duplikatów
            user.profile.update_total_points()

    @staticmethod
    def _calculate_single_prediction(actual_home, actual_away, pred_home, pred_away, is_doubled):
        """Czysta funkcja biznesowa do matematycznego wyliczenia punktów"""
        points = 0

        # 1. Dokładny wynik (3 punkty)
        if actual_home == pred_home and actual_away == pred_away:
            points = 3
        else:
            actual_diff = actual_home - actual_away
            pred_diff = pred_home - pred_away

            # 2. Poprawny zwycięzca / remis
            if (actual_diff > 0 and pred_diff > 0) or \
                    (actual_diff < 0 and pred_diff < 0) or \
                    (actual_diff == 0 and pred_diff == 0):

                # Poprawna różnica bramek (2 punkty)
                if actual_diff == pred_diff:
                    points = 2
                # Tylko poprawny zwycięzca (1 punkt)
                else:
                    points = 1

        # Mnożnik za podwojenie
        if is_doubled:
            points *= 2

        return points