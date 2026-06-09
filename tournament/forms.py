from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Profile, Match


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean(self):
        # Ta metoda odpala się po kliknięciu wyślij, ale ZANIM dane trafią do bazy
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            # Odpalamy błąd - formularz zostanie oznaczony jako NIEPOPRAWNY
            self.add_error('password_confirm', "Podane hasła nie zgadzają się!")

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