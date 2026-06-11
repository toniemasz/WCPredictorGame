from tournament.models import Match, MatchWatch
from tournament.services.team_name_service import TeamNameService


class MatchWatchService:
    @classmethod
    def get_watch_context(cls, user, country_language="pl"):
        entries = list(
            MatchWatch.objects.select_related(
                "match",
                "match__home_team",
                "match__away_team",
            )
            .filter(user=user, want_to_watch=True)
            .order_by("match__kickoff")
        )
        for entry in entries:
            TeamNameService.annotate_match(entry.match, country_language)

        return {
            "entries": entries,
            "to_watch_count": sum(1 for entry in entries if not entry.watched),
            "watched_count": sum(1 for entry in entries if entry.watched),
        }

    @staticmethod
    def get_entries_by_match(user):
        if not user or not user.is_authenticated:
            return {}

        return {
            entry.match_id: entry
            for entry in MatchWatch.objects.filter(user=user)
        }

    @classmethod
    def update_entry(cls, user, match_id, action):
        match = Match.objects.get(pk=match_id)
        entry, _ = MatchWatch.objects.get_or_create(
            user=user,
            match=match,
        )

        if action == "add":
            entry.want_to_watch = True
        elif action == "remove":
            entry.want_to_watch = False
            entry.watched = False
        elif action == "watched":
            entry.want_to_watch = True
            entry.watched = True
        elif action == "unwatched":
            entry.watched = False
        else:
            raise ValueError("Nieznana akcja listy do obejrzenia.")

        entry.save(update_fields=["want_to_watch", "watched", "updated_at"])
        return entry
