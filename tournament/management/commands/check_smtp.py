from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from tournament.services.account_security_service import AccountSecurityService


class Command(BaseCommand):
    help = "Checks SMTP settings and optionally sends a test email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            default=None,
            help="Recipient for the test email. Defaults to EMAIL_HOST_USER.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print sanitized SMTP settings without sending an email.",
        )

    def handle(self, *args, **options):
        diagnostics = AccountSecurityService.email_config_diagnostics()
        self.stdout.write("SMTP diagnostics:")
        for key, value in diagnostics.items():
            self.stdout.write(f"- {key}: {value}")

        if options["dry_run"]:
            return

        recipient = options["to"] or settings.EMAIL_HOST_USER
        if not recipient:
            raise CommandError("Provide --to or set EMAIL_HOST_USER.")

        try:
            send_mail(
                "WCPredictor SMTP test",
                "SMTP configuration works. This is a test message from WCPredictor.",
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(
                f"SMTP test failed: {exc.__class__.__name__}: {exc}"
            ) from exc

        self.stdout.write(self.style.SUCCESS(f"SMTP test email sent to {recipient}."))
