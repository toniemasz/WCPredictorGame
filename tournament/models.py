from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Team(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)

    def __str__(self):
        return self.name


class Match(models.Model):

    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('LIVE', 'Live'),
        ('FINISHED', 'Finished'),
    )

    home_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='home_matches'
    )

    away_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='away_matches'
    )

    kickoff = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SCHEDULED'
    )

    home_score = models.IntegerField(
        null=True,
        blank=True
    )

    away_score = models.IntegerField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"


class Prediction(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE
    )

    predicted_home = models.IntegerField()

    predicted_away = models.IntegerField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    points = models.IntegerField(
        default=0
    )

    class Meta:
        unique_together = ('user', 'match')

class Profile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True
    )

    points = models.IntegerField(
        default=0
    )

    def __str__(self):
        return self.user.username



@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):

    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):

    instance.profile.save()