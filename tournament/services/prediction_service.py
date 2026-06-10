# tournament/services/prediction_service.py
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from tournament.models import Prediction, Match, BonusUsage


class PredictionService:
    @staticmethod
    @transaction.atomic
    def save_prediction(user, match_id: int, data: dict) -> dict:
        match = PredictionService._get_match(match_id)
        PredictionService._validate_match_is_open(match)

        home = data.get("predicted_home")
        away = data.get("predicted_away")
        PredictionService._validate_score_input(home, away)

        is_doubled = data.get("is_doubled", False)
        limit = PredictionService._get_bonus_limit()
        bonus_usage = PredictionService._get_bonus_usage(user, match.stage)
        existing = PredictionService._get_existing_prediction(user, match)

        PredictionService._update_bonus_usage(
            bonus_usage,
            is_doubled,
            existing.is_doubled if existing else False,
            limit,
        )
        PredictionService._save_prediction(user, match, data)

        return {
            "status": "success",
            "bonus_remaining": limit - bonus_usage.count,
            "stage": match.stage,
            "limit_reached": bonus_usage.count >= limit
        }

    @staticmethod
    def _get_match(match_id):
        return Match.objects.get(pk=match_id)

    @staticmethod
    def _validate_match_is_open(match):
        if timezone.now() >= match.kickoff:
            raise ValueError("Mecz już się rozpoczął! Bonus i typ zostały zamrożone.")

    @staticmethod
    def _validate_score_input(home, away):
        if home is None or away is None or home == "" or away == "":
            raise ValueError("Wpisz obie wartości wyniku.")

    @staticmethod
    def _get_bonus_limit():
        return getattr(settings, 'BONUS_LIMIT_PER_STAGE', 2)

    @staticmethod
    def _get_bonus_usage(user, stage):
        bonus_usage, _ = BonusUsage.objects.select_for_update().get_or_create(
            user=user,
            stage=stage
        )
        return bonus_usage

    @staticmethod
    def _get_existing_prediction(user, match):
        return Prediction.objects.select_for_update().filter(
            user=user,
            match=match
        ).first()

    @staticmethod
    def _update_bonus_usage(bonus_usage, is_doubled, had_bonus_before, limit):
        if is_doubled and not had_bonus_before:
            if bonus_usage.count >= limit:
                raise ValueError(f"Wykorzystałeś limit bonusów ({limit}) w tej rundzie.")
            bonus_usage.count += 1
            bonus_usage.save()

        elif had_bonus_before and not is_doubled and bonus_usage.count > 0:
            bonus_usage.count -= 1
            bonus_usage.save()

    @staticmethod
    def _save_prediction(user, match, data):
        home = data.get("predicted_home")
        away = data.get("predicted_away")
        is_doubled = data.get("is_doubled", False)

        Prediction.objects.update_or_create(
            user=user,
            match=match,
            defaults={
                "predicted_home": home,
                "predicted_away": away,
                "is_doubled": is_doubled,
                "predicted_first_team": data.get("predicted_first_team"),
                "predicted_scorer": data.get("predicted_scorer"),
            }
        )
