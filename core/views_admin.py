from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication

from .permissions import IsSystemAdmin


# --- LOGIN ADMIN ---
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login_view(request):
    try:
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            return Response({'message': 'Identifiants incorrects'}, status=401)

        if not user.is_staff and not user.is_superuser:
            return Response({'message': 'Accès refusé : Espace réservé au personnel.'}, status=403)

        refresh = RefreshToken.for_user(user)

        return Response({
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}".strip(),
                'role': 'admin'
            }
        })
    except Exception as e:
        return Response({'message': str(e)}, status=500)


# --- STATISTIQUES (DASHBOARD) ---
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_stats_view(request):
    total_coaches = User.objects.filter(coach_profile__isnull=False).count()
    total_athletes = User.objects.filter(client_profile__isnull=False).count()
    pending_kyc = User.objects.filter(coach_profile__isnull=False, is_active=False).count()

    return Response({
        "total_coaches": total_coaches,
        "total_athletes": total_athletes,
        "total_revenue": 452102,
        "pending_kyc": pending_kyc,
        "gym_partners": 312
    })


# --- GESTION DES COACHS ---
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_coach_list(request):
    coach_users = User.objects.filter(coach_profile__isnull=False).order_by('-date_joined')

    data = []
    for user in coach_users:
        specialty = "Général"

        if hasattr(user, 'coach_profile') and user.coach_profile.specialites_tags:
            if isinstance(user.coach_profile.specialites_tags, list) and len(user.coach_profile.specialites_tags) > 0:
                specialty = user.coach_profile.specialites_tags[0]
            elif isinstance(user.coach_profile.specialites_tags, str):
                specialty = user.coach_profile.specialites_tags

        data.append({
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "specialty": specialty,
            "date": user.date_joined.strftime("%b %d, %Y"),
            "status": "Validated" if user.is_active else "Suspended"
        })

    return Response(data)


# --- GESTION DES ATHLÈTES ---
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_athlete_list(request):
    athlete_users = User.objects.filter(client_profile__isnull=False).select_related(
        'client_profile',
        'client_profile__coach__user'
    ).order_by('-date_joined')

    data = []
    for user in athlete_users:
        coach_name = None

        if hasattr(user, 'client_profile') and user.client_profile.coach and user.client_profile.coach.user:
            coach_user = user.client_profile.coach.user
            coach_name = f"{coach_user.first_name} {coach_user.last_name}".strip() or coach_user.email

        data.append({
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "coach_name": coach_name,
            "date": user.date_joined.strftime("%b %d, %Y"),
            "status": "Active" if user.is_active else "Inactive"
        })

    return Response(data)


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_delete_athlete(request, pk):
    try:
        user = User.objects.get(id=pk, client_profile__isnull=False)
        user.delete()

        return Response({
            "message": "Athlète supprimé définitivement"
        }, status=200)
    except User.DoesNotExist:
        return Response({"error": "Athlète introuvable"}, status=404)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_toggle_coach_status(request, pk):
    try:
        user = User.objects.get(id=pk, coach_profile__isnull=False)
        action = request.data.get('action')

        user.is_active = (action == 'validate')
        user.save()

        return Response({
            "message": "Statut mis à jour",
            "status": "Validated" if user.is_active else "Suspended"
        })
    except User.DoesNotExist:
        return Response({"error": "Coach introuvable"}, status=404)