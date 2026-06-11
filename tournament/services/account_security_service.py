import secrets
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.signing import salted_hmac
from django.core.validators import validate_email
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from tournament.models import AccountSecurityCode


logger = logging.getLogger(__name__)


class AccountSecurityService:
    CODE_TTL = timedelta(minutes=15)
    PASSWORD_RESET_SESSION_EMAIL = "password_reset_email"
    HIDE_MISSING_EMAIL_WARNING_SESSION_KEY = "hide_missing_email_warning"
    HIDE_MISSING_EMAIL_WARNING_COOKIE = "hide_missing_email_warning"
    HIDE_MISSING_EMAIL_WARNING_COOKIE_AGE = 60 * 60 * 24 * 365

    @classmethod
    def request_password_reset(cls, email):
        email = cls.normalize_email(email)
        user = cls._get_unique_active_user_by_email(email)

        if not user:
            return False

        code = cls._create_code(
            user,
            email,
            AccountSecurityCode.PURPOSE_PASSWORD_RESET,
        )
        cls._send_code_email(
            email,
            "Kod do zmiany hasła WCPredictor",
            (
                "Otrzymaliśmy prośbę o zmianę hasła.\n\n"
                f"Twój kod: {code}\n"
                "Kod jest ważny przez 15 minut.\n\n"
                "Jeżeli to nie Ty, zignoruj tę wiadomość."
            ),
        )
        return True

    @staticmethod
    def uses_console_email_backend():
        return settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"

    @classmethod
    def reset_password(cls, email, code, new_password, password_confirm):
        email = cls.normalize_email(email)
        user = cls._get_unique_active_user_by_email(email)
        if not user:
            raise ValueError("Kod jest nieprawidłowy albo wygasł.")

        if new_password != password_confirm:
            raise ValueError("Podane hasła nie są identyczne.")

        try:
            password_validation.validate_password(new_password, user)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        security_code = cls._get_valid_code(
            user,
            email,
            AccountSecurityCode.PURPOSE_PASSWORD_RESET,
            code,
        )
        if not security_code:
            raise ValueError("Kod jest nieprawidłowy albo wygasł.")

        user.set_password(new_password)
        user.save(update_fields=["password"])
        cls._mark_code_used(security_code)
        return user

    @classmethod
    def start_email_change(cls, user, email):
        email = cls.normalize_email(email)

        if cls._email_belongs_to_other_user(user, email):
            raise ValueError("Ten adres e-mail jest już przypisany do innego konta.")

        code = cls._create_code(
            user,
            email,
            AccountSecurityCode.PURPOSE_EMAIL_CHANGE,
        )
        cls._send_code_email(
            email,
            "Kod potwierdzający adres e-mail WCPredictor",
            (
                "Potwierdź dodanie tego adresu e-mail do konta WCPredictor.\n\n"
                f"Twój kod: {code}\n"
                "Kod jest ważny przez 15 minut.\n\n"
                "Adres zostanie zapisany dopiero po podaniu kodu w aplikacji."
            ),
        )
        return email

    @classmethod
    def confirm_email_change(cls, user, code):
        security_code = cls._get_valid_code(
            user,
            None,
            AccountSecurityCode.PURPOSE_EMAIL_CHANGE,
            code,
        )
        if not security_code:
            raise ValueError("Kod jest nieprawidłowy albo wygasł.")

        if cls._email_belongs_to_other_user(user, security_code.email):
            cls._mark_code_used(security_code)
            raise ValueError("Ten adres e-mail jest już przypisany do innego konta.")

        user.email = security_code.email
        user.save(update_fields=["email"])
        cls._mark_code_used(security_code)
        return user

    @classmethod
    def get_pending_email_change(cls, user):
        return (
            AccountSecurityCode.objects.filter(
                user=user,
                purpose=AccountSecurityCode.PURPOSE_EMAIL_CHANGE,
                used_at__isnull=True,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def remember_missing_email_warning(cls, request):
        request.session[cls.HIDE_MISSING_EMAIL_WARNING_SESSION_KEY] = True

    @classmethod
    def apply_missing_email_warning_cookie(cls, response):
        response.set_cookie(
            cls.HIDE_MISSING_EMAIL_WARNING_COOKIE,
            "1",
            max_age=cls.HIDE_MISSING_EMAIL_WARNING_COOKIE_AGE,
            samesite="Lax",
            secure=not settings.DEBUG,
        )
        return response

    @classmethod
    def _create_code(cls, user, email, purpose):
        now = timezone.now()
        AccountSecurityCode.objects.filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
        ).update(used_at=now)

        code = cls._generate_code()
        AccountSecurityCode.objects.create(
            user=user,
            purpose=purpose,
            email=email,
            code_hash=cls._hash_code(user, email, code),
            expires_at=now + cls.CODE_TTL,
        )
        return code

    @staticmethod
    def _generate_code():
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def _get_valid_code(cls, user, email, purpose, code):
        code = (code or "").strip()
        if not code:
            return None

        query = AccountSecurityCode.objects.filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
        )
        if email:
            query = query.filter(email__iexact=email)

        for security_code in query.order_by("-created_at"):
            if constant_time_compare(
                security_code.code_hash,
                cls._hash_code(user, security_code.email, code),
            ):
                return security_code

        return None

    @classmethod
    def _hash_code(cls, user, email, code):
        return salted_hmac(
            "tournament.account_security_code",
            f"{user.pk}:{email.lower()}:{code}",
            secret=settings.SECRET_KEY,
        ).hexdigest()

    @staticmethod
    def _mark_code_used(security_code):
        security_code.used_at = timezone.now()
        security_code.save(update_fields=["used_at"])

    @classmethod
    def normalize_email(cls, email):
        email = (email or "").strip().lower()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValueError("Podaj poprawny adres e-mail.") from exc
        return email

    @staticmethod
    def _get_unique_active_user_by_email(email):
        users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
        if len(users) != 1:
            return None
        return users[0]

    @staticmethod
    def _email_belongs_to_other_user(user, email):
        return User.objects.filter(
            Q(email__iexact=email),
        ).exclude(pk=user.pk).exists()

    @staticmethod
    def _send_code_email(email, subject, message):
        try:
            send_mail(
                subject,
                message,
                getattr(settings, "DEFAULT_FROM_EMAIL", None),
                [email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("Failed to send security code email to %s", email)
            raise ValueError(
                "Nie udało się wysłać maila z kodem. Sprawdź konfigurację SMTP na serwerze."
            ) from exc
