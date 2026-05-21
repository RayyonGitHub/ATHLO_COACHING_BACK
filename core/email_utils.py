from django.conf import settings
from django.core.mail import EmailMultiAlternatives


# ─── Platform helper ──────────────────────────────────────────────────────────

def link_for_platform(platform: str, mobile_path: str, web_path: str) -> str:
    """
    Return the single correct URL for the given platform.
    mobile_path: path appended to athlo:// or the Expo dev base (e.g. "reset-password?uid=X&token=Y")
    web_path:    path appended to FRONTEND_URL           (e.g. "reset-password?uid=X&token=Y")
    """
    if platform == "mobile":
        expo_dev_url = getattr(settings, "EXPO_DEV_URL", None)
        if expo_dev_url:
            return f"{expo_dev_url}/--/{mobile_path}"
        return f"athlo://{mobile_path}"
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    return f"{frontend_url}/{web_path}"


# ─── HTML builder ─────────────────────────────────────────────────────────────

def _cta_button(label: str, url: str, color: str = "#FF6B00") -> str:
    return (
        f'<a href="{url}" target="_blank" '
        f'style="display:inline-block;background-color:{color};color:#FFFFFF;'
        f'font-weight:700;font-size:15px;text-decoration:none;padding:14px 32px;'
        f'border-radius:10px;letter-spacing:0.2px;mso-padding-alt:0;">'
        f'{label}</a>'
    )


def _build_html(greeting: str, paragraphs: list, cta_label: str, cta_url: str, note: str = "") -> str:
    paras_html = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;color:#374151;line-height:1.7;">{p}</p>'
        for p in paragraphs
    )
    note_html = (
        f'<p style="margin:24px 0 0;font-size:12px;color:#9CA3AF;line-height:1.6;">{note}</p>'
        if note else ""
    )
    cta_html = _cta_button(cta_label, cta_url) if cta_label and cta_url else ""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>ATHLO</title>
</head>
<body style="margin:0;padding:0;background-color:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F3F4F6;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">

          <!-- ── Header ── -->
          <tr>
            <td style="background-color:#0B0B0F;padding:24px 36px;border-radius:16px 16px 0 0;">
              <span style="font-size:26px;font-weight:900;font-style:italic;letter-spacing:-1px;color:#FFFFFF;font-family:Georgia,serif;">ATH</span><span style="font-size:26px;font-weight:900;font-style:italic;letter-spacing:-1px;color:#FF6B00;font-family:Georgia,serif;">LO</span>
            </td>
          </tr>

          <!-- ── Body ── -->
          <tr>
            <td style="background-color:#FFFFFF;padding:36px 36px 32px;">
              <p style="margin:0 0 20px;font-size:18px;font-weight:700;color:#111827;">{greeting}</p>
              {paras_html}
              <div style="margin:28px 0 0;">
                {cta_html}
              </div>
              {note_html}
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="background-color:#F9FAFB;padding:18px 36px;border-top:1px solid #E5E7EB;border-radius:0 0 16px 16px;">
              <p style="margin:0;font-size:12px;color:#9CA3AF;line-height:1.7;">
                Si vous n'êtes pas à l'origine de cette action, ignorez simplement cet email.<br>
                &copy; ATHLO &mdash; <em>Forge ton futur</em>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_plain(greeting: str, paragraphs: list, cta_label: str, cta_url: str, note: str = "") -> str:
    import re
    clean = [re.sub(r"<[^>]+>", "", p) for p in paragraphs]
    lines = [greeting, ""] + clean
    if cta_label and cta_url:
        lines += ["", f"{cta_label} :", cta_url]
    if note:
        clean_note = re.sub(r"<[^>]+>", "", note)
        lines += ["", clean_note]
    lines += ["", "L'équipe ATHLO"]
    return "\n".join(lines)


# ─── Public send function ─────────────────────────────────────────────────────

def send_html_email(
    subject: str,
    to: str,
    greeting: str,
    paragraphs: list,
    cta_label: str = "",
    cta_url: str = "",
    note: str = "",
) -> None:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER)
    plain = _build_plain(greeting, paragraphs, cta_label, cta_url, note)
    html  = _build_html(greeting, paragraphs, cta_label, cta_url, note)
    msg = EmailMultiAlternatives(subject=subject, body=plain, from_email=from_email, to=[to])
    msg.attach_alternative(html, "text/html")
    msg.send()
