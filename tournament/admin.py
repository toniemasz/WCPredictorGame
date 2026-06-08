# tournament/admin.py
from django.contrib import admin
from datetime import timedelta
from .models import Match, Team, Prediction, Profile, TeamPlayer


# --- 1. Definicja akcji dla panelu Admina ---
@admin.action(description="Wymuś dodanie +2 godzin do czasu meczu (kickoff)")
def add_two_hours_to_kickoff(modeladmin, request, queryset):
    for match in queryset:
        if match.kickoff:
            # Dodajemy fizycznie 2 godziny do rekordu w bazie
            match.kickoff = match.kickoff + timedelta(hours=2)
            match.save()

    modeladmin.message_user(request, f"Sukces! Dodano +2 godziny do {queryset.count()} meczów.")


# --- 2. Rejestracja modelu Match z przypisaną akcją ---
# Używamy dekoratora @admin.register, aby stworzyć zaawansowany widok
@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'home_team', 'away_team', 'kickoff', 'status')
    actions = [add_two_hours_to_kickoff]  # Podpinamy nasz nowy przycisk


# --- 3. Rejestracja pozostałych modeli ---
# (Jeśli masz je już gdzieś indziej, nie powielaj tego wpisu)
admin.site.register(Team)
admin.site.register(Prediction)
admin.site.register(Profile)
admin.site.register(TeamPlayer)

