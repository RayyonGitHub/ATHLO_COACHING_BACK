import requests
from django.conf import settings

# --- STRAVA API ---
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

def exchange_strava_code_for_tokens(code):
    response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    
    # --- NOUVEAU : On affiche la vraie erreur de Strava ! ---
    if not response.ok:
        print("\n" + "="*40)
        print("🚨 ERREUR RENVOYÉE PAR STRAVA :")
        print(response.text)
        print("="*40 + "\n")
        raise Exception(f"Strava a refusé le code: {response.text}")
        
    return response.json()

from datetime import timedelta
import datetime
from django.utils import timezone
from .models import ActiviteExterne

# --- NOUVELLES FONCTIONS DE SYNCHRONISATION STRAVA ---

def ensure_valid_strava_token(client):
    """Vérifie si le token Strava est valide, sinon le rafraîchit."""
    if not client.strava_refresh_token:
        return None

    # Si le token expire dans plus de 5 minutes, on le garde
    if client.strava_access_token and client.strava_token_expires_at:
        if client.strava_token_expires_at > timezone.now() + timedelta(minutes=5):
            return client.strava_access_token

    # Sinon, on doit le rafraîchir
    response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "refresh_token": client.strava_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    
    if not response.ok:
        print("Erreur refresh token Strava:", response.text)
        return None
        
    token_data = response.json()
    
    client.strava_access_token = token_data.get("access_token")
    client.strava_refresh_token = token_data.get("refresh_token")
    expires_at_timestamp = token_data.get("expires_at")
    
    if expires_at_timestamp:
        client.strava_token_expires_at = datetime.datetime.fromtimestamp(
            expires_at_timestamp, 
            tz=datetime.timezone.utc
        )
    client.save()
    
    return client.strava_access_token


def sync_strava_activities_for_client(client):
    """Télécharge les dernières activités Strava et les sauvegarde en base."""
    token = ensure_valid_strava_token(client)
    if not token:
        raise Exception("Impossible d'obtenir un jeton d'accès Strava valide.")

    # On demande les 30 dernières activités
    url = "https://www.strava.com/api/v3/athlete/activities?per_page=30"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers, timeout=20)
    
    if not response.ok:
        raise Exception(f"Erreur lors de la récupération des activités: {response.text}")
        
    activities = response.json()
    saved_count = 0
    
    for act in activities:
        external_id = str(act.get("id"))
        
        # On vérifie si on a déjà enregistré cette activité pour ne pas faire de doublons
        if not ActiviteExterne.objects.filter(external_id=external_id).exists():
            
            # Strava renvoie la date en format ISO string, on la convertit
            date_str = act.get("start_date")
            date_obj = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else timezone.now()

            ActiviteExterne.objects.create(
                client=client,
                plateforme='STRAVA',
                external_id=external_id,
                nom=act.get("name", "Activité Strava"),
                type_activite=act.get("type", "Inconnu"),
                date_debut=date_obj,
                distance_metres=act.get("distance"),
                temps_secondes=act.get("moving_time"),
                frequence_cardiaque_moyenne=act.get("average_heartrate"),
                calories=act.get("calories"), # Parfois absent selon la montre
                donnees_brutes=act  # On stocke tout au cas où on a besoin d'autres métriques plus tard !
            )
            saved_count += 1
            
    return saved_count

# Note : La logique Garmin sera ajoutée ici plus tard selon le même principe.