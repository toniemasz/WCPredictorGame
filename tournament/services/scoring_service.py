class ScoringService:
    @staticmethod
    def get_rules_explanation():
        """Zwraca zasady punktacji do wyświetlenia jako tooltip we frontendzie."""
        return (
            "Zasady punktacji:\n"
            "• Dokładny wynik bramkowy: +3 punkty\n"
            "• Poprawny typ (kierunek: wygrana/remis/przegrana): +1 punkt\n"
            "• Poprawna drużyna strzelająca pierwszego gola: +1 punkt\n"
            "• Poprawny pierwszy strzelec: +2 punkty\n"
            "• Bonus x2: podwaja całkowitą sumę punktów z meczu."
        )

    @staticmethod
    def calculate_points(match, prediction):
        """Zwraca krotkę (total_points, breakdown_dict)"""
        if match.status != 'FINISHED' or match.home_score is None or match.away_score is None:
            return 0, {}

        points = 0
        breakdown = {}

        # 1. Wynik meczu
        if prediction.predicted_home == match.home_score and prediction.predicted_away == match.away_score:
            points += 3
            breakdown['exact_score'] = {"name": "Dokładny wynik", "points": 3}
        else:
            pred_diff = prediction.predicted_home - prediction.predicted_away
            actual_diff = match.home_score - match.away_score
            if (pred_diff > 0 and actual_diff > 0) or (pred_diff < 0 and actual_diff < 0) or (
                    pred_diff == 0 and actual_diff == 0):
                points += 1
                breakdown['correct_outcome'] = {"name": "Poprawny typ (kierunek)", "points": 1}

        # 2. Pierwsza bramka (drużyna)
        if prediction.predicted_first_team and match.first_scoring_team:
            if prediction.predicted_first_team == match.first_scoring_team:
                points += 1
                breakdown['first_team'] = {"name": "Trafiona drużyna (1. gol)", "points": 1}

        # 3. Pierwszy strzelec
        if prediction.predicted_scorer and match.first_scorer:
            if prediction.predicted_scorer.lower() == match.first_scorer.lower():
                points += 2
                breakdown['first_scorer'] = {"name": "Trafiony pierwszy strzelec", "points": 2}

        # 4. Bonus
        if prediction.is_doubled and points > 0:
            base_points = points
            points *= 2
            breakdown['bonus'] = {"name": "Bonus x2", "points": base_points}  # Pokazuje wartość podwojenia

        return points, breakdown

    @classmethod
    def recalculate_match(cls, match):
        """Metoda wywoływana przy zapisie rozstrzygniętego meczu"""
        predictions = match.prediction_set.all()
        for pred in predictions:
            total_points, breakdown = cls.calculate_points(match, pred)
            pred.points = total_points
            pred.points_breakdown = breakdown
            pred.save(update_fields=['points', 'points_breakdown'])