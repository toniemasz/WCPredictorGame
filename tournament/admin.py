from django.contrib import admin
from .models import Team, Match, Prediction

admin.site.register(Team)
admin.site.register(Match)
admin.site.register(Prediction)