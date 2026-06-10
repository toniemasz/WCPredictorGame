# tournament/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist


class Team(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)
    name_pl = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class Match(models.Model):
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('LIVE', 'Live'),
        ('FINISHED', 'Finished'),
    )

    TEAM_CHOICES = (
        ('HOME', 'Gospodarze'),
        ('AWAY', 'Goście'),
        ('NONE', 'Brak bramek')
    )

    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    kickoff = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    stage = models.CharField(max_length=50, default="GROUP_STAGE")

    home_odds = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    draw_odds = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    away_odds = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    odds_api_event_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True
    )
    football_data_match_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True
    )

    first_scoring_team = models.CharField(max_length=10, choices=TEAM_CHOICES, null=True, blank=True)
    first_scorer = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Wpisz nazwisko zawodnika, który strzelił pierwszą bramkę w meczu"
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


        if self.home_score is not None and self.away_score is not None:
            from tournament.services.scoring_service import ScoringService
            ScoringService.recalculate_match(self)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"


class Prediction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    predicted_home = models.IntegerField()
    predicted_away = models.IntegerField()

    predicted_first_team = models.CharField(max_length=10, choices=Match.TEAM_CHOICES, null=True, blank=True)
    predicted_scorer = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    points = models.IntegerField(default=0)
    is_doubled = models.BooleanField(default=False)
    points_breakdown = models.JSONField(null=True, blank=True)
    class Meta:
        unique_together = ('user', 'match')


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.CharField(max_length=255, default='default.png')
    points = models.IntegerField(default=0)

    def __str__(self):
        return self.user.username

    def update_total_points(self):
        """Pomocnicza metoda aktualizująca łączne punkty na profilu"""
        total = sum(p.points for p in self.user.prediction_set.all())
        self.points = total
        self.save(update_fields=['points'])

class TeamPlayer(models.Model):
    api_player_id = models.BigIntegerField(unique=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="players"
    )

    name = models.CharField(max_length=100)
    position = models.CharField(max_length=10, null=True, blank=True)
    jersey_number = models.CharField(max_length=10, null=True, blank=True)

    def __str__(self):
        return self.name

class BonusUsage(models.Model):
    user  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bonus_usages')
    stage = models.CharField(max_length=50)
    count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('user', 'stage')

    def __str__(self):
        return f"{self.user} | {self.stage} | {self.count}"


class ApiSyncStatus(models.Model):
    SYNC_MATCHES = "matches"

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_PENDING, "W toku"),
        (STATUS_SUCCESS, "Zaktualizowano"),
        (STATUS_ERROR, "Błąd aktualizacji"),
    )

    sync_name = models.CharField(max_length=50, unique=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    processed_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.sync_name}: {self.get_status_display()}"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except ObjectDoesNotExist:
        Profile.objects.create(user=instance)

