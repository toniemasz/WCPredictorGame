from django.contrib import admin

from .models import (
    Team,
    Match,
    Prediction,
    Profile
)
from .services.scoring_service import ScoringService

@admin.action(description="Przelicz punkty dla zaznaczonych meczów")
def recalculate_points(modeladmin, request, queryset):
    count = 0
    for match in queryset:
        if match.status in ['LIVE', 'FINISHED']:
            ScoringService.calculate_points_for_match(match)
            count += 1

    modeladmin.message_user(request, f"Pomyślnie przeliczono punkty dla {count} meczów.", messages.SUCCESS)


class MatchAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'kickoff', 'status', 'stage', 'home_score', 'away_score')
    actions = [recalculate_points]


admin.site.register(Team)
admin.site.register(Match)
admin.site.register(Prediction)
admin.site.register(Profile)