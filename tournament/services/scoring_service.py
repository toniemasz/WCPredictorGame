class ScoringService:
    @staticmethod
    def get_rules_explanation():
        return (
            "Zasady punktacji:\n"
            "• Dokładny wynik bramkowy: +3 punkty\n"
            "• Poprawny typ (kierunek: 1X2): +1 punkt\n"
            "• Poprawna drużyna (1. gol): +1 punkt\n"
            "• Poprawny pierwszy strzelec: +2 punkty\n"
            "• Bonus x2: podwaja całkowitą sumę punktów."
        )

    @staticmethod
    def calculate_points(match, prediction):
        if match.status != 'FINISHED' or match.home_score is None or match.away_score is None:
            return 0, {}

        points = 0
        breakdown = {}

        # 1. Wynik meczu (Dokładny vs Kierunek)
        if prediction.predicted_home == match.home_score and prediction.predicted_away == match.away_score:
            points += 3
            breakdown['exact_score'] = {"name": "Dokładny wynik", "points": 3}
        else:
            pred_diff = prediction.predicted_home - prediction.predicted_away
            actual_diff = match.home_score - match.away_score
            if (pred_diff > 0 and actual_diff > 0) or (pred_diff < 0 and actual_diff < 0) or (
                    pred_diff == 0 and actual_diff == 0):
                points += 1
                breakdown['correct_outcome'] = {"name": "Poprawny typ", "points": 1}


        if match.home_score == 0 and match.away_score == 0:
            if prediction.predicted_first_team == 'NONE':
                points += 1
                breakdown['first_team'] = {"name": "Poprawny brak bramek (drużyna)", "points": 1}
        elif prediction.predicted_first_team and match.first_scoring_team:
            if prediction.predicted_first_team == match.first_scoring_team:
                points += 1
                breakdown['first_team'] = {"name": "Trafiona drużyna (1. gol)", "points": 1}

        # 3. Pierwszy strzelec
        # Jeśli mecz to 0:0, gracz nie powinien dostać punktów za strzelca chyba że system przewiduje obstawienie "Brak" w liście zawodników.
        # Założenie: w przypadku bramek sprawdzamy wpis admina.
        if prediction.predicted_scorer and match.first_scorer:
            if prediction.predicted_scorer.strip().lower() == match.first_scorer.strip().lower():
                points += 2
                breakdown['first_scorer'] = {"name": "Trafiony strzelec", "points": 2}

        # 4. Bonus x2
        if prediction.is_doubled and points > 0:
            base_points = points
            points *= 2
            breakdown['bonus'] = {"name": "Bonus x2", "points": base_points}

        return points, breakdown

    @classmethod
    def recalculate_match(cls, match):
        predictions = match.prediction_set.all()
        for pred in predictions:
            total_points, breakdown = cls.calculate_points(match, pred)
            pred.points = total_points
            pred.points_breakdown = breakdown
            pred.save(update_fields=['points', 'points_breakdown'])