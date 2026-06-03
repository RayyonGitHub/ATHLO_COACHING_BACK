from datetime import timedelta
import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from .integrations_service import exchange_strava_code_for_tokens, sync_strava_activities_for_client
from .serializers import ActiviteExterneSerializer
from .integrations_service import exchange_strava_code_for_tokens
from .models import ActiviteExterne, Client

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def integrations_status(request):
    """Renvoie l'état des connexions de l'athlète à Strava et Garmin"""
    if not hasattr(request.user, 'client_profile'):
        return Response({"detail": "Réservé aux athlètes."}, status=403)

    client = request.user.client_profile
    
    return Response({
        "strava_connected": bool(client.strava_refresh_token),
        "garmin_connected": bool(client.garmin_refresh_token),
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def strava_connect(request):
    if not hasattr(request.user, 'client_profile'):
        return Response({"detail": "Réservé aux athlètes."}, status=403)

    code = request.data.get("code")
    if not code:
        return Response({"detail": "Code Strava manquant."}, status=400)

    try:
        token_data = exchange_strava_code_for_tokens(code)
        
        client = request.user.client_profile
        client.strava_access_token = token_data.get("access_token")
        client.strava_refresh_token = token_data.get("refresh_token")
        expires_at_timestamp = token_data.get("expires_at") # Strava renvoie un timestamp UNIX
        
        if expires_at_timestamp:
            client.strava_token_expires_at = datetime.datetime.fromtimestamp(
                expires_at_timestamp, 
                tz=datetime.timezone.utc
            )
        # Strava renvoie aussi les infos du profil dans 'athlete'
        athlete_data = token_data.get("athlete", {})
        if athlete_data:
            client.strava_athlete_id = str(athlete_data.get("id"))

        client.save()

        return Response({"message": "Compte Strava connecté avec succès.", "connected": True})
        
    except Exception as e:
        return Response({"detail": f"Erreur lors de la connexion à Strava: {str(e)}"}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def strava_disconnect(request):
    if not hasattr(request.user, 'client_profile'):
        return Response({"detail": "Réservé aux athlètes."}, status=403)

    client = request.user.client_profile
    client.strava_access_token = None
    client.strava_refresh_token = None
    client.strava_token_expires_at = None
    client.strava_athlete_id = None
    client.save()

    return Response({"message": "Compte Strava déconnecté.", "connected": False})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def strava_sync(request):
    """Déclenche la synchronisation manuelle des activités Strava."""
    if not hasattr(request.user, 'client_profile'):
        return Response({"detail": "Réservé aux athlètes."}, status=403)

    client = request.user.client_profile
    
    if not client.strava_refresh_token:
        return Response({"detail": "Compte Strava non connecté."}, status=400)

    try:
        new_activities_count = sync_strava_activities_for_client(client)
        return Response({
            "message": f"Synchronisation terminée avec succès.",
            "nouvelles_activites": new_activities_count
        })
    except Exception as e:
        return Response({"detail": f"Erreur lors de la synchronisation : {str(e)}"}, status=500)
    

   # ... après strava_sync ...

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_external_activities(request):
    """Récupère toutes les activités externes de l'athlète connecté."""
    if not hasattr(request.user, 'client_profile'):
        return Response({"detail": "Réservé aux athlètes."}, status=403)
        
    activites = ActiviteExterne.objects.filter(client=request.user.client_profile).order_by('-date_debut')
    serializer = ActiviteExterneSerializer(activites, many=True)
    return Response(serializer.data)