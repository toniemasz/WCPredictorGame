from io import StringIO
import re

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from tournament.models import AccountSecurityCode
from tournament.services.account_security_service import AccountSecurityService


def _extract_code(message):
    match = re.search(r"Twój kod: (\d{6})", message.body)
    assert match
    return match.group(1)


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_requires_email_code(client, user):
    user.email = "tester@example.com"
    user.save(update_fields=["email"])

    response = client.post(
        reverse("forgot_password_stage1"),
        {"email": "tester@example.com"},
    )

    assert response.status_code == 302
    assert response.url == reverse("password_reset_stage2")
    assert len(mail.outbox) == 1
    code = _extract_code(mail.outbox[0])

    response = client.post(
        reverse("password_reset_stage2"),
        {
            "email": "tester@example.com",
            "code": "000000",
            "new_password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        },
    )
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("pass") is True
    assert "Kod jest nieprawidłowy albo wygasł." in response.content.decode()

    response = client.post(
        reverse("password_reset_stage2"),
        {
            "email": "tester@example.com",
            "code": code,
            "new_password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        },
    )
    user.refresh_from_db()
    security_code = AccountSecurityCode.objects.get(
        user=user,
        purpose=AccountSecurityCode.PURPOSE_PASSWORD_RESET,
    )

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert user.check_password("StrongPass123!") is True
    assert security_code.used_at is not None


@pytest.mark.django_db
def test_old_username_only_password_reset_does_not_change_password(client, user):
    response = client.post(
        reverse("password_reset_stage2"),
        {
            "username": user.username,
            "new_password": "StrongPass123!",
        },
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("pass") is True


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_change_is_saved_only_after_code_confirmation(client, user):
    client.force_login(user)

    response = client.post(
        reverse("request_email_verification"),
        {
            "email": "new@example.com",
            "next": reverse("profile"),
        },
    )

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("profile")
    assert user.email == ""
    assert len(mail.outbox) == 1
    code = _extract_code(mail.outbox[0])

    response = client.post(
        reverse("confirm_email_verification"),
        {"code": "000000"},
    )
    user.refresh_from_db()
    assert response.status_code == 302
    assert user.email == ""

    response = client.post(
        reverse("confirm_email_verification"),
        {"code": code},
    )
    user.refresh_from_db()

    assert response.status_code == 302
    assert user.email == "new@example.com"


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_change_code_can_be_resent(client, user):
    client.force_login(user)

    client.post(
        reverse("request_email_verification"),
        {
            "email": "new@example.com",
            "next": reverse("profile"),
        },
    )
    response = client.get(reverse("profile"))
    assert "Wyślij kod ponownie" in response.content.decode()

    response = client.post(
        reverse("request_email_verification"),
        {
            "email": "new@example.com",
            "next": reverse("profile"),
        },
    )

    assert response.status_code == 302
    assert len(mail.outbox) == 2
    assert AccountSecurityCode.objects.filter(
        user=user,
        purpose=AccountSecurityCode.PURPOSE_EMAIL_CHANGE,
        used_at__isnull=True,
    ).count() == 1


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_code_can_be_resent_from_confirm_page(client, user):
    user.email = "tester@example.com"
    user.save(update_fields=["email"])

    client.post(reverse("forgot_password_stage1"), {"email": "tester@example.com"})
    response = client.get(reverse("password_reset_stage2"))

    assert "Wyślij kod ponownie" in response.content.decode()

    response = client.post(reverse("forgot_password_stage1"), {"email": "tester@example.com"})

    assert response.status_code == 302
    assert len(mail.outbox) == 2
    assert AccountSecurityCode.objects.filter(
        user=user,
        purpose=AccountSecurityCode.PURPOSE_PASSWORD_RESET,
        used_at__isnull=True,
    ).count() == 1


@pytest.mark.django_db
def test_password_reset_email_send_error_is_shown_on_request_page(client, monkeypatch, user):
    user.email = "tester@example.com"
    user.save(update_fields=["email"])

    def broken_send_mail(*args, **kwargs):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(
        "tournament.services.account_security_service.send_mail",
        broken_send_mail,
    )

    response = client.post(
        reverse("forgot_password_stage1"),
        {"email": "tester@example.com"},
    )

    assert response.status_code == 200
    assert "Nie udało się wysłać maila z kodem." in response.content.decode()


@pytest.mark.django_db
def test_password_reset_resend_email_error_stays_on_confirm_page(client, monkeypatch, user):
    user.email = "tester@example.com"
    user.save(update_fields=["email"])

    def broken_send_mail(*args, **kwargs):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(
        "tournament.services.account_security_service.send_mail",
        broken_send_mail,
    )

    response = client.post(
        reverse("forgot_password_stage1"),
        {
            "email": "tester@example.com",
            "next": reverse("password_reset_stage2"),
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.redirect_chain == [(reverse("password_reset_stage2"), 302)]
    assert "Nie udało się wysłać maila z kodem." in response.content.decode()
    assert "Ustaw nowe hasło" in response.content.decode()


@override_settings(
    EMAIL_HOST_USER="sender@example.com",
    EMAIL_HOST_PASSWORD="very-secret-password",
    DEFAULT_FROM_EMAIL="WCPredictor <sender@example.com>",
)
def test_email_config_diagnostics_do_not_expose_password():
    diagnostics = AccountSecurityService.email_config_diagnostics()

    assert diagnostics["host_password_set"] is True
    assert "very-secret-password" not in str(diagnostics)


@override_settings(
    EMAIL_HOST="smtp.example.com",
    EMAIL_HOST_USER="sender@example.com",
    EMAIL_HOST_PASSWORD="very-secret-password",
)
def test_check_smtp_command_dry_run_outputs_diagnostics():
    output = StringIO()

    call_command("check_smtp", "--dry-run", stdout=output)

    content = output.getvalue()
    assert "SMTP diagnostics" in content
    assert "smtp.example.com" in content
    assert "very-secret-password" not in content


@pytest.mark.django_db
def test_missing_email_warning_can_be_hidden_for_session(client, user):
    client.force_login(user)

    response = client.get(reverse("profile"))
    assert "Wymagany e-mail do odzyskania hasła" in response.content.decode()

    response = client.post(
        reverse("request_email_verification"),
        {
            "remember_missing_email_warning": "on",
            "next": reverse("profile"),
        },
    )
    assert response.status_code == 302
    assert response.cookies["hide_missing_email_warning"].value == "1"

    client.logout()
    client.cookies["hide_missing_email_warning"] = "1"
    client.force_login(user)

    response = client.get(reverse("profile"))
    assert "Wymagany e-mail do odzyskania hasła" not in response.content.decode()
