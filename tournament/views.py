from django.shortcuts import render

from tournament.models import Match
from tournament.services.import_service import ImportService


def match_list(request):

    if Match.objects.count() == 0:
        ImportService.import_matches()

    matches = Match.objects.order_by("kickoff")

    return render(
        request,
        "tournament/match_list.html",
        {
            "matches": matches
        }
    )