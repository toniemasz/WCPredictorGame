# tournament/services/prediction_service.py
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from tournament.models import Prediction, Match, BonusUsage


class PredictionService:
    @staticmethod
    @transaction.atomic
    def save_prediction(user, match_id: int, data: dict) -> dict:
        match = Match.objects.get(pk=match_id)

        # 1. Zabezpieczenie przed zmianą po rozpoczęciu meczu.
        if timezone.now() >= match.kickoff:
            raise ValueError("Mecz już się rozpoczął! Bonus i typ zostały zamrożone.")

        home = data.get("predicted_home")
        away = data.get("predicted_away")
        is_doubled = data.get("is_doubled", False)

        if home is None or away is None or home == "" or away == "":
            raise ValueError("Wpisz obie wartości wyniku.")

        limit = getattr(settings, 'BONUS_LIMIT_PER_STAGE', 2)

        # 2. Blokada wiersza licznika bonusów (zapobiega race conditions)
        bonus_usage, _ = BonusUsage.objects.select_for_update().get_or_create(
            user=user,
            stage=match.stage
        )

        # 3. Blokada wiersza istniejącego typu
        existing = Prediction.objects.select_for_update().filter(
            user=user, match=match
        ).first()

        had_bonus_before = existing.is_doubled if existing else False

        # 4. Logika dodawania/odejmowania
        if is_doubled and not had_bonus_before:
            if bonus_usage.count >= limit:
                raise ValueError(f"Wykorzystałeś limit bonusów ({limit}) w tej rundzie.")
            bonus_usage.count += 1
            bonus_usage.save()

        elif had_bonus_before and not is_doubled:
            if bonus_usage.count > 0:
                bonus_usage.count -= 1
                bonus_usage.save()

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

        return {
            "status": "success",
            "bonus_remaining": limit - bonus_usage.count,
            "stage": match.stage
        }