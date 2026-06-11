from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from tournament.models import MatchComment, MatchCommentReaction
from tournament.services.comment_service import MatchCommentService
from tournament.services.match_service import MatchListService


@pytest.mark.django_db
def test_logged_user_can_add_comment(client, user, future_match):
    client.force_login(user)

    response = client.post(
        reverse("add_match_comment", args=[future_match.id]),
        {"content": "Dobry mecz do typowania."},
    )

    assert response.status_code == 302
    assert MatchComment.objects.filter(
        user=user,
        match=future_match,
        content="Dobry mecz do typowania.",
    ).exists()


@pytest.mark.django_db
def test_anonymous_user_cannot_add_comment(client, future_match):
    response = client.post(
        reverse("add_match_comment", args=[future_match.id]),
        {"content": "Anonimowy komentarz"},
    )

    assert response.status_code == 302
    assert MatchComment.objects.count() == 0


@pytest.mark.django_db
def test_empty_comment_is_not_saved(client, user, future_match):
    client.force_login(user)

    response = client.post(
        reverse("add_match_comment", args=[future_match.id]),
        {"content": "   "},
    )

    assert response.status_code == 302
    assert MatchComment.objects.count() == 0


@pytest.mark.django_db
def test_too_long_comment_is_not_saved(user, future_match):
    with pytest.raises(ValueError, match="maksymalnie"):
        MatchCommentService.add_comment(
            user,
            future_match.id,
            "x" * 501,
        )

    assert MatchComment.objects.count() == 0


@pytest.mark.django_db
def test_comments_are_assigned_to_specific_match(user, make_match):
    first = make_match()
    second = make_match(stage="Runda 2")

    comment = MatchCommentService.add_comment(user, first.id, "Komentarz tylko pod pierwszym.")

    assert comment.match == first
    assert MatchCommentService.get_match_comments(first, user)[0].content == "Komentarz tylko pod pierwszym."
    assert MatchCommentService.get_match_comments(second, user) == []


@pytest.mark.django_db
def test_author_can_delete_own_comment(user, future_match):
    comment = MatchCommentService.add_comment(user, future_match.id, "Do usunięcia")

    deleted = MatchCommentService.delete_comment(user, comment.id)

    deleted.refresh_from_db()
    assert deleted.is_deleted is True


@pytest.mark.django_db
def test_regular_user_cannot_delete_other_users_comment(user, other_user, future_match):
    comment = MatchCommentService.add_comment(other_user, future_match.id, "Nie mój komentarz")

    with pytest.raises(PermissionError):
        MatchCommentService.delete_comment(user, comment.id)

    comment.refresh_from_db()
    assert comment.is_deleted is False


@pytest.mark.django_db
def test_superuser_can_delete_any_comment(future_match):
    owner = User.objects.create_user(username="owner", password="pass")
    admin = User.objects.create_superuser(username="admin", password="pass", email="admin@example.com")
    comment = MatchCommentService.add_comment(owner, future_match.id, "Admin może usunąć")

    MatchCommentService.delete_comment(admin, comment.id)

    comment.refresh_from_db()
    assert comment.is_deleted is True


@pytest.mark.django_db
def test_delete_comment_requires_post_method(client, user, future_match):
    comment = MatchCommentService.add_comment(user, future_match.id, "Tylko POST")
    client.force_login(user)

    response = client.get(reverse("delete_match_comment", args=[comment.id]))

    assert response.status_code == 405
    comment.refresh_from_db()
    assert comment.is_deleted is False


@pytest.mark.django_db
def test_match_card_comment_count_is_calculated(user, future_match):
    MatchCommentService.add_comment(user, future_match.id, "Licznik komentarzy")

    context = MatchListService.get_match_list_context(user)
    match = context["stage_groups"][0]["matches"][0]

    assert match.comment_count == 1


@pytest.mark.django_db
def test_match_detail_template_shows_form_only_for_logged_users(client, user, future_match):
    anonymous_response = client.get(reverse("match_detail", args=[future_match.id]))

    assert "Zaloguj się" in anonymous_response.content.decode()
    assert "Dodaj komentarz" not in anonymous_response.content.decode()

    client.force_login(user)
    logged_response = client.get(reverse("match_detail", args=[future_match.id]))

    assert "Dodaj komentarz" in logged_response.content.decode()


@pytest.mark.django_db
def test_match_detail_template_shows_author_date_and_content(client, user, future_match):
    comment = MatchCommentService.add_comment(user, future_match.id, "Treść komentarza")
    client.force_login(user)

    response = client.get(reverse("match_detail", args=[future_match.id]))
    content = response.content.decode()

    assert user.username in content
    assert "Treść komentarza" in content
    assert comment.created_at.strftime("%d.%m.%Y") in content


@pytest.mark.django_db
def test_duplicate_comment_is_blocked(user, future_match):
    MatchCommentService.add_comment(user, future_match.id, "Ten sam komentarz")

    with pytest.raises(ValueError, match="identycznego"):
        MatchCommentService.add_comment(user, future_match.id, "ten sam komentarz")

    assert MatchComment.objects.count() == 1


@pytest.mark.django_db
def test_rate_limit_blocks_more_than_five_comments_per_minute(user, future_match):
    now = timezone.now()
    for index in range(MatchCommentService.RATE_LIMIT):
        MatchCommentService.add_comment(
            user,
            future_match.id,
            f"Komentarz {index}",
            now=now + timedelta(seconds=index),
        )

    with pytest.raises(ValueError, match="Za dużo komentarzy"):
        MatchCommentService.add_comment(
            user,
            future_match.id,
            "Szósty komentarz",
            now=now + timedelta(seconds=30),
        )

    assert MatchComment.objects.count() == MatchCommentService.RATE_LIMIT


@pytest.mark.django_db
def test_user_can_react_once_and_reaction_count_is_calculated(user, future_match):
    comment = MatchCommentService.add_comment(user, future_match.id, "Pod reakcję")

    MatchCommentService.toggle_reaction(user, comment.id, "good")
    MatchCommentService.toggle_reaction(user, comment.id, "fire")
    comments = MatchCommentService.get_match_comments(future_match, user)

    assert MatchCommentReaction.objects.count() == 1
    assert MatchCommentReaction.objects.get().reaction == "fire"
    assert comments[0].reaction_counts["fire"] == 1
    assert comments[0].current_user_reaction == "fire"


@pytest.mark.django_db
def test_reaction_toggle_removes_existing_reaction(user, future_match):
    comment = MatchCommentService.add_comment(user, future_match.id, "Pod cofnięcie")

    MatchCommentService.toggle_reaction(user, comment.id, "good")
    MatchCommentService.toggle_reaction(user, comment.id, "good")

    assert MatchCommentReaction.objects.count() == 0
