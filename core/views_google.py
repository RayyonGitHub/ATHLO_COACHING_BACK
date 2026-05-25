from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .google_calendar import exchange_code_for_tokens
from .models import Coach


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def google_calendar_status(request):
    if not hasattr(request.user, 'coach_profile'):
        return Response({"connected": False, "detail": "Réservé aux coachs."}, status=403)

    coach = request.user.coach_profile
    connected = bool(coach.google_refresh_token or coach.google_access_token)

    return Response({
        "connected": connected,
        "expires_at": coach.google_token_expires_at,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def google_calendar_connect(request):
    # Si l'utilisateur n'a pas encore de profil coach (inscription en cours), le créer.
    coach, _ = Coach.objects.get_or_create(user=request.user)

    code = request.data.get("code")
    if not code:
        return Response({"detail": "Code Google manquant."}, status=400)

    token_data = exchange_code_for_tokens(code)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token:
        return Response(token_data, status=400)

    coach.google_access_token = access_token

    if refresh_token:
        coach.google_refresh_token = refresh_token

    coach.google_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    coach.save()

    return Response({
        "message": "Google Calendar connecté avec succès.",
        "connected": True,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def google_calendar_disconnect(request):
    if not hasattr(request.user, 'coach_profile'):
        return Response({"detail": "Réservé aux coachs."}, status=403)

    coach = request.user.coach_profile
    coach.google_access_token = None
    coach.google_refresh_token = None
    coach.google_token_expires_at = None
    coach.save(update_fields=[
        "google_access_token",
        "google_refresh_token",
        "google_token_expires_at",
    ])

    return Response({
        "message": "Google Calendar déconnecté.",
        "connected": False,
    })