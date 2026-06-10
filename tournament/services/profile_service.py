from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.templatetags.static import static

from tournament.models import Match, Prediction, Profile


class ProfileService:
    AVATAR_DIR = "avatars"
    DEFAULT_AVATAR = "default.png"
    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

    @classmethod
    def get_target_user(cls, current_user, user_id=None):
        if user_id:
            return get_object_or_404(User, pk=user_id)

        return current_user

    @classmethod
    def get_profile_context(cls, current_user, user_id=None, target_user=None):
        target_user = target_user or cls.get_target_user(current_user, user_id)
        profile, _ = Profile.objects.get_or_create(user=target_user)
        profile.avatar_url = cls.get_avatar_url(profile.avatar)

        is_owner = current_user == target_user

        return {
            "target_user": target_user,
            "profile": profile,
            "profile_avatar_url": profile.avatar_url,
            "available_avatars": (
                cls.get_available_avatar_options(profile.avatar)
                if is_owner
                else []
            ),
            "matches_by_stage": cls.get_user_matches_by_stage(target_user),
            "debug_path": str(cls.get_static_avatar_dir()),
        }

    @classmethod
    def update_profile(cls, current_user, target_user, post_data):
        if current_user != target_user:
            return False

        profile, _ = Profile.objects.get_or_create(user=target_user)
        changed = False

        new_username = (post_data.get("username") or "").strip()
        if new_username and new_username != current_user.username:
            try:
                current_user.username = new_username
                current_user.save(update_fields=["username"])
                changed = True
            except IntegrityError as exc:
                raise ValueError("Ta nazwa użytkownika jest już zajęta.") from exc

        new_avatar = (post_data.get("avatar") or "").strip()
        allowed_avatar_values = {
            option["value"]
            for option in cls.get_available_avatar_options(profile.avatar)
        }

        if new_avatar in allowed_avatar_values and new_avatar != profile.avatar:
            profile.avatar = new_avatar
            profile.save(update_fields=["avatar"])
            changed = True

        return changed

    @classmethod
    def get_leaderboard_profiles(cls):
        profiles = list(
            Profile.objects.select_related("user")
            .annotate(
                total_points=Coalesce(
                    Sum("user__prediction__points"),
                    Value(0),
                )
            )
            .order_by("-total_points", "user__username")
        )

        for profile in profiles:
            profile.avatar_url = cls.get_avatar_url(profile.avatar)

        return profiles

    @classmethod
    def get_user_matches_by_stage(cls, user):
        matches = Match.objects.select_related(
            "home_team", "away_team"
        ).order_by("kickoff")

        predictions = Prediction.objects.filter(user=user)
        predictions_by_match_id = {
            prediction.match_id: prediction
            for prediction in predictions
        }

        matches_by_stage = {}
        for match in matches:
            match.target_prediction = predictions_by_match_id.get(match.id)
            matches_by_stage.setdefault(match.stage, []).append(match)

        return matches_by_stage

    @classmethod
    def get_available_avatar_options(cls, selected_avatar=None):
        avatar_values = []

        for avatar_file in cls._iter_avatar_files(cls.get_static_avatar_dir()):
            avatar_values.append(avatar_file.name)

        for avatar_file in cls._iter_avatar_files(cls.get_media_avatar_dir()):
            avatar_values.append(f"{cls.AVATAR_DIR}/{avatar_file.name}")

        options = []
        seen_values = set()

        for value in avatar_values:
            if value in seen_values:
                continue

            seen_values.add(value)
            options.append({
                "value": value,
                "url": cls.get_avatar_url(value),
                "selected": cls._avatar_values_match(selected_avatar, value),
            })

        return sorted(options, key=lambda option: option["value"].lower())

    @classmethod
    def get_avatar_url(cls, avatar_value):
        avatar_value = (avatar_value or cls.DEFAULT_AVATAR).strip()

        if avatar_value.startswith(("http://", "https://", "/")):
            return avatar_value

        normalized_path = str(PurePosixPath(avatar_value))

        if "/" in normalized_path:
            if cls._media_file_exists(normalized_path):
                return cls._join_url(settings.MEDIA_URL, normalized_path)
            if cls._static_file_exists(normalized_path):
                return static(normalized_path)
            return cls.get_default_avatar_url()

        media_avatar_path = f"{cls.AVATAR_DIR}/{normalized_path}"
        if cls._media_file_exists(media_avatar_path):
            return cls._join_url(settings.MEDIA_URL, media_avatar_path)

        static_avatar_path = f"{cls.AVATAR_DIR}/{normalized_path}"
        if cls._static_file_exists(static_avatar_path):
            return static(static_avatar_path)

        return cls.get_default_avatar_url()

    @classmethod
    def get_default_avatar_url(cls):
        return static(f"{cls.AVATAR_DIR}/{cls.DEFAULT_AVATAR}")

    @classmethod
    def get_static_avatar_dir(cls):
        static_dirs = getattr(settings, "STATICFILES_DIRS", [])
        if static_dirs:
            return Path(static_dirs[0]) / cls.AVATAR_DIR

        return Path(settings.BASE_DIR) / "static" / cls.AVATAR_DIR

    @classmethod
    def get_media_avatar_dir(cls):
        return Path(settings.MEDIA_ROOT) / cls.AVATAR_DIR

    @classmethod
    def _iter_avatar_files(cls, avatar_dir):
        if not avatar_dir.exists():
            return []

        return [
            avatar_file
            for avatar_file in avatar_dir.iterdir()
            if (
                avatar_file.is_file()
                and avatar_file.suffix.lower() in cls.IMAGE_EXTENSIONS
            )
        ]

    @classmethod
    def _avatar_values_match(cls, current_value, option_value):
        if current_value == option_value:
            return True

        if not current_value:
            return option_value == cls.DEFAULT_AVATAR

        return PurePosixPath(current_value).name == PurePosixPath(option_value).name

    @classmethod
    def _media_file_exists(cls, relative_path):
        return (Path(settings.MEDIA_ROOT) / relative_path).exists()

    @classmethod
    def _static_file_exists(cls, relative_path):
        return any(
            (Path(static_dir) / relative_path).exists()
            for static_dir in getattr(settings, "STATICFILES_DIRS", [])
        )

    @staticmethod
    def _join_url(base_url, relative_path):
        return f"{base_url.rstrip('/')}/{relative_path.lstrip('/')}"
