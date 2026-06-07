from django.contrib import admin

from .models import (
    Team,
    Match,
    Prediction,
    Profile
)

admin.site.register(Team)
admin.site.register(Match)
admin.site.register(Prediction)
admin.site.register(Profile)