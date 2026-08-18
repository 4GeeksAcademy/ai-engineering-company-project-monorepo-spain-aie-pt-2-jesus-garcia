import os

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "TrackFlow <onboarding@resend.dev>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{FRONTEND_URL}/reset-password?token={token}"

    if not RESEND_API_KEY:
        print(
            "[email_service] RESEND_API_KEY no configurada. "
            f"Enlace de restablecimiento para {to_email}: {link}"
        )
        return

    try:
        import resend

        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Restablece tu contraseña en TrackFlow",
            "html": (
                "<p>Recibimos una solicitud para restablecer tu contraseña.</p>"
                f'<p><a href="{link}">Restablecer contraseña</a></p>'
                "<p>Si no solicitaste este cambio, ignora este email.</p>"
            ),
        })
    except Exception as exc:  # noqa: BLE001
        print(
            f"[email_service] Error enviando email a {to_email}: {exc}. "
            f"Enlace: {link}"
        )
