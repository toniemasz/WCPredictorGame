# tournament/admin.py
from django.contrib import admin
from datetime import timedelta
from .models import Match, Team, Prediction, Profile, TeamPlayer
from django.contrib import admin
from django import forms
from .models import Match, Team, TeamPlayer, Prediction, Profile


@admin.action(description="Wymuś dodanie +2 godzin do czasu meczu (kickoff)")
def add_two_hours_to_kickoff(modeladmin, request, queryset):
    for match in queryset:
        if match.kickoff:
            # Dodajemy fizycznie 2 godziny do rekordu w bazie
            match.kickoff = match.kickoff + timedelta(hours=2)
            match.save()

    modeladmin.message_user(request, f"Sukces! Dodano +2 godziny do {queryset.count()} meczów.")





class MatchAdminForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Sprawdzamy, czy edytujemy istniejący mecz (musi mieć przypisane drużyny, by pobrać zawodników)
        if self.instance and self.instance.pk:
            home_team = self.instance.home_team
            away_team = self.instance.away_team

            home_name = home_team.name if home_team else 'Drużyna Domowa'
            away_name = away_team.name if away_team else 'Drużyna Wyjazdowa'

            # 1. Dynamiczne etykiety dla wyboru pierwszej drużyny strzelającej
            self.fields['first_scoring_team'].choices = [
                ('', '---------'),
                ('HOME', home_name),
                ('AWAY', away_name),
                ('NONE', 'Brak bramek (No goals)')
            ]

            # 2. Dynamiczna lista zawodników dla pola first_scorer
            if home_team and away_team:
                # Pobieramy graczy tylko dla wybranych 2 drużyn
                players = TeamPlayer.objects.filter(
                    team__in=[home_team, away_team]
                ).select_related('team').order_by('team__name', 'name')

                player_choices = [('', '--------- (Wybierz strzelca)')]

                for p in players:
                    # Format wyświetlania: "Nazwisko (Reprezentacja)"
                    player_choices.append((p.name, f"{p.name} ({p.team.name})"))

                # Zastępujemy domyślny CharField rozwijaną listą (ChoiceField)
                self.fields['first_scorer'] = forms.ChoiceField(
                    choices=player_choices,
                    required=False,
                    label="Pierwszy strzelec",
                    help_text="Zawodnicy pobrani z bazy wyłącznie dla tych dwóch krajów."
                )

                # Zabezpieczenie: jeśli w bazie jest już wpisany strzelec ręcznie i nie ma go na liście
                current_scorer = self.instance.first_scorer
                if current_scorer and current_scorer not in [c[0] for c in player_choices]:
                    player_choices.append((current_scorer, f"{current_scorer} (wpisany ręcznie)"))
                    self.fields['first_scorer'].choices = player_choices


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    form = MatchAdminForm
    list_display = ('home_team', 'away_team', 'kickoff', 'status', 'home_score', 'away_score')
    list_filter = ('status', 'stage')
    search_fields = ('home_team__name', 'away_team__name')


# Rejestracja pozostałych modeli w panelu admina
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(TeamPlayer)
class TeamPlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'position')
    list_filter = ('team', 'position')
    search_fields = ('name',)


admin.site.register(Prediction)
admin.site.register(Profile)
