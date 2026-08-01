"""Envoi d'emails (invitations). Sans SMTP configuré, l'envoi est simplement
sauté — le lien d'invitation reste disponible dans la réponse API / la page Équipe."""

import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(get_settings().smtp_host)


def send_invitation_email(to: str, invite_url: str, organization: str) -> bool:
    """Envoie le lien d'invitation par email. Retourne True si envoyé."""
    settings = get_settings()
    if not settings.smtp_host:
        return False

    message = EmailMessage()
    message["Subject"] = f"Invitation à rejoindre {organization}"
    message["From"] = settings.smtp_from
    message["To"] = to
    message.set_content(
        f"Bonjour,\n\n"
        f"Vous êtes invité(e) à rejoindre l'organisation « {organization} » sur "
        f"la plateforme de vidéosurveillance.\n\n"
        f"Activez votre compte via ce lien (valable 7 jours) :\n{invite_url}\n\n"
        f"Si vous n'attendiez pas cette invitation, ignorez ce message."
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        logger.info("invitation email sent to %s", to)
        return True
    except Exception:
        logger.exception("failed to send invitation email to %s", to)
        return False
