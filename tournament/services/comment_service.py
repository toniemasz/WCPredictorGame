from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from tournament.models import Match, MatchComment, MatchCommentReaction, Profile
from tournament.services.profile_service import ProfileService


class MatchCommentService:
    RATE_LIMIT = 5
    RATE_LIMIT_WINDOW = timedelta(minutes=1)

    @classmethod
    def get_match_comments(cls, match, user=None):
        comments = list(
            MatchComment.objects.select_related("user", "user__profile")
            .prefetch_related("reactions")
            .filter(match=match, is_deleted=False)
            .annotate(reaction_count=Count("reactions"))
            .order_by("-created_at", "-id")
        )

        for comment in comments:
            profile, _ = Profile.objects.get_or_create(user=comment.user)
            comment.avatar_url = ProfileService.get_avatar_url(profile.avatar)
            comment.can_delete = cls.can_delete_comment(user, comment)
            comment.reaction_choices = MatchCommentReaction.REACTION_CHOICES
            comment.reaction_counts = cls._get_reaction_counts(comment)
            comment.current_user_reaction = cls._get_user_reaction(comment, user)

        return comments

    @classmethod
    def add_comment(cls, user, match_id, content, now=None):
        match = Match.objects.get(pk=match_id)
        now = now or timezone.now()
        cleaned_content = cls._clean_content(content)

        cls._validate_content(cleaned_content)
        cls._validate_not_duplicate(user, match, cleaned_content)
        cls._validate_rate_limit(user, now)

        return MatchComment.objects.create(
            user=user,
            match=match,
            content=cleaned_content,
        )

    @classmethod
    def delete_comment(cls, user, comment_id):
        comment = MatchComment.objects.select_related("user", "match").get(pk=comment_id)
        if not cls.can_delete_comment(user, comment):
            raise PermissionError("Nie możesz usunąć tego komentarza.")

        comment.is_deleted = True
        comment.save(update_fields=["is_deleted", "updated_at"])
        return comment

    @classmethod
    def toggle_reaction(cls, user, comment_id, reaction):
        if reaction not in dict(MatchCommentReaction.REACTION_CHOICES):
            raise ValueError("Nieznana reakcja.")

        comment = MatchComment.objects.get(pk=comment_id, is_deleted=False)
        existing = MatchCommentReaction.objects.filter(
            user=user,
            comment=comment,
        ).first()

        if existing and existing.reaction == reaction:
            existing.delete()
            return None

        if existing:
            existing.reaction = reaction
            existing.save(update_fields=["reaction"])
            return existing

        return MatchCommentReaction.objects.create(
            user=user,
            comment=comment,
            reaction=reaction,
        )

    @staticmethod
    def can_delete_comment(user, comment):
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or comment.user_id == user.id

    @staticmethod
    def get_comment_counts_by_match():
        return {
            item["match_id"]: item["count"]
            for item in MatchComment.objects.filter(is_deleted=False)
            .values("match_id")
            .annotate(count=Count("id"))
        }

    @staticmethod
    def _clean_content(content):
        return (content or "").strip()

    @staticmethod
    def _validate_content(content):
        if not content:
            raise ValueError("Komentarz nie może być pusty.")
        if len(content) > MatchComment.MAX_LENGTH:
            raise ValueError(f"Komentarz może mieć maksymalnie {MatchComment.MAX_LENGTH} znaków.")

    @staticmethod
    def _validate_not_duplicate(user, match, content):
        last_comment = MatchComment.objects.filter(
            user=user,
            match=match,
            is_deleted=False,
        ).order_by("-created_at", "-id").first()

        if last_comment and last_comment.content.strip().lower() == content.lower():
            raise ValueError("Nie wysyłaj identycznego komentarza pod rząd.")

    @classmethod
    def _validate_rate_limit(cls, user, now):
        comment_count = MatchComment.objects.filter(
            user=user,
            created_at__gte=now - cls.RATE_LIMIT_WINDOW,
            is_deleted=False,
        ).count()

        if comment_count >= cls.RATE_LIMIT:
            raise ValueError("Za dużo komentarzy w krótkim czasie. Spróbuj ponownie za minutę.")

    @staticmethod
    def _get_reaction_counts(comment):
        counts = {
            reaction: 0
            for reaction in dict(MatchCommentReaction.REACTION_CHOICES)
        }

        for reaction in comment.reactions.all():
            counts[reaction.reaction] = counts.get(reaction.reaction, 0) + 1

        return counts

    @staticmethod
    def _get_user_reaction(comment, user):
        if not user or not user.is_authenticated:
            return None

        for reaction in comment.reactions.all():
            if reaction.user_id == user.id:
                return reaction.reaction

        return None
