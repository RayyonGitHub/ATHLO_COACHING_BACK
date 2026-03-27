import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_EVENTS_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def exchange_code_for_tokens(code):
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token):
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def ensure_valid_google_token(coach):
    if coach.google_access_token and coach.google_token_expires_at:
        if coach.google_token_expires_at > timezone.now() + timedelta(minutes=1):
            return coach.google_access_token

    if not coach.google_refresh_token:
        return None

    token_data = refresh_access_token(coach.google_refresh_token)
    coach.google_access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in", 3600)
    coach.google_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    coach.save(update_fields=["google_access_token", "google_token_expires_at"])

    return coach.google_access_token


def _build_event_payload(title, date_value, start_time, end_time, description):
    start_dt = f"{date_value.isoformat()}T{start_time.strftime('%H:%M:%S')}"
    end_dt = f"{date_value.isoformat()}T{end_time.strftime('%H:%M:%S')}"

    return {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_dt,
            "timeZone": "Europe/Paris",
        },
        "end": {
            "dateTime": end_dt,
            "timeZone": "Europe/Paris",
        },
    }


def upsert_google_event_for_seance(seance):
    coach = seance.coach
    token = ensure_valid_google_token(coach)
    if not token:
        return None

    if not seance.jour_prevu or not seance.heure_debut or not seance.heure_fin:
        if seance.google_event_id:
            delete_google_event(coach, seance.google_event_id)
            type(seance).objects.filter(id=seance.id).update(google_event_id=None)
        return None

    payload = _build_event_payload(
        title=seance.titre or "Séance ATHLO",
        date_value=seance.jour_prevu,
        start_time=seance.heure_debut,
        end_time=seance.heure_fin,
        description="Séance ATHLO synchronisée automatiquement",
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if seance.google_event_id:
        response = requests.patch(
            f"{GOOGLE_EVENTS_BASE_URL}/{seance.google_event_id}",
            json=payload,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    response = requests.post(
        GOOGLE_EVENTS_BASE_URL,
        json=payload,
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    event_data = response.json()

    type(seance).objects.filter(id=seance.id).update(
        google_event_id=event_data.get("id")
    )
    return event_data


def upsert_google_event_for_indisponibilite(indispo):
    coach = indispo.coach
    token = ensure_valid_google_token(coach)
    if not token:
        return None

    if not indispo.jour_prevu or not indispo.heure_debut or not indispo.heure_fin:
        if indispo.google_event_id:
            delete_google_event(coach, indispo.google_event_id)
            type(indispo).objects.filter(id=indispo.id).update(google_event_id=None)
        return None

    description = "Congé ATHLO synchronisé automatiquement" if indispo.est_conge else "Indisponibilité ATHLO synchronisée automatiquement"

    payload = _build_event_payload(
        title=indispo.titre or ("Congé" if indispo.est_conge else "Indisponibilité"),
        date_value=indispo.jour_prevu,
        start_time=indispo.heure_debut,
        end_time=indispo.heure_fin,
        description=description,
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if indispo.google_event_id:
        response = requests.patch(
            f"{GOOGLE_EVENTS_BASE_URL}/{indispo.google_event_id}",
            json=payload,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    response = requests.post(
        GOOGLE_EVENTS_BASE_URL,
        json=payload,
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    event_data = response.json()

    type(indispo).objects.filter(id=indispo.id).update(
        google_event_id=event_data.get("id")
    )
    return event_data


def delete_google_event(coach, google_event_id):
    if not google_event_id:
        return

    token = ensure_valid_google_token(coach)
    if not token:
        return

    headers = {
        "Authorization": f"Bearer {token}",
    }

    response = requests.delete(
        f"{GOOGLE_EVENTS_BASE_URL}/{google_event_id}",
        headers=headers,
        timeout=20,
    )

    if response.status_code not in (200, 204, 404):
        response.raise_for_status()