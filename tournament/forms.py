from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Profile, Match


class RegisterForm(forms.ModelForm):
    email = forms.EmailField()

    password = forms.CharField(
        widget=forms.PasswordInput
    )

    password_confirm = forms.CharField(
        widget=forms.PasswordInput
    )

    avatar = forms.ImageField(
        required=False
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password"
        ]

    # NOWA METODA: Walidacja rozmiaru avatara
    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")

        if avatar:
            limit_mb = 2
            # Przeliczamy megabajty na bajty (2 * 1024 * 1024)
            if avatar.size > limit_mb * 1024 * 1024:
                raise ValidationError(f"Zbyt duży plik. Maksymalny rozmiar avatara to {limit_mb} MB.")

        return avatar

    # Twoja dotychczasowa walidacja haseł
    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError(
                "Hasła nie są identyczne."
            )

        return cleaned_data


class PredictionForm(forms.Form):
    predicted_home = forms.IntegerField(
        min_value=0
    )

    predicted_away = forms.IntegerField(
        min_value=0
    )

    predicted_first_team = forms.ChoiceField(
        choices=Match.TEAM_CHOICES,
        required=False
    )
    predicted_scorer = forms.CharField(
        max_length=100,
        required=False
    )