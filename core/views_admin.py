from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Coach, Client, Salle
from .permissions import IsSystemAdmin
from .serializers import SalleSerializer
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
            return Response({'message': 'Accès refusé.'}, status=403)
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

# --- STATS ---
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_stats_view(request):
    total_coaches = User.objects.filter(coach_profile__isnull=False).count()
    total_athletes = User.objects.filter(client_profile__isnull=False).count()
    pending_kyc = User.objects.filter(coach_profile__isnull=False, is_active=False).count()
    gym_partners = Salle.objects.count()
    return Response({
        "total_coaches": total_coaches,
        "total_athletes": total_athletes,
        "total_revenue": 452102,
        "pending_kyc": pending_kyc,
        "gym_partners": gym_partners
    })
# --- NOUVELLE GESTION DES SALLES (CRUD ADMIN) ---
@api_view(['GET', 'POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_salle_list_create(request):
    if request.method == 'GET':
        salles = Salle.objects.all().order_by('-id')
        data = []
        for s in salles:
            data.append({
                "id": s.id,
                "nom": s.nom,
                "adresse": s.adresse,
                "ville": s.ville,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "nb_coachs": s.coachs_affilies.count() # Utilise le related_name défini dans models.py
            })
        return Response(data)

    elif request.method == 'POST':
        serializer = SalleSerializer(data=request.data)
        if serializer.is_valid():
            s = serializer.save()
            return Response({
                "id": s.id, 
                "nom": s.nom, 
                "adresse": s.adresse, 
                "ville": s.ville, 
                "nb_coachs": 0
            }, status=201)
        return Response(serializer.errors, status=400)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_salle_delete(request, pk):
    try:
        salle = Salle.objects.get(pk=pk)
        salle.delete()
        return Response({"message": "Salle supprimée"}, status=204)
    except Salle.DoesNotExist:
        return Response({"error": "Salle introuvable"}, status=404)
    
# --- GESTION UTILISATEURS ---
@api_view(['PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_update_user(request, pk):
    try:
        user = User.objects.get(pk=pk)
        data = request.data
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.save()
        return Response({"message": "Utilisateur mis à jour"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_change_password(request, pk):
    try:
        user = User.objects.get(pk=pk)
        pwd = request.data.get('password')
        if not pwd: return Response({"error": "Manquant"}, status=400)
        user.password = make_password(pwd)
        user.save()
        return Response({"message": "Mot de passe changé"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_toggle_user_status(request, pk):
    try:
        user = User.objects.get(id=pk)
        action = request.data.get('action')
        user.is_active = (action in ['activate', 'validate'])
        user.save()
        return Response({"status": "Validated" if user.is_active else "Suspended"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_coach_list(request):
    coaches = User.objects.filter(coach_profile__isnull=False)
    return Response([{
        "id": u.id, "first_name": u.first_name, "last_name": u.last_name,
        "name": f"{u.first_name} {u.last_name}", "email": u.email,
        "status": "Validated" if u.is_active else "Suspended"
    } for u in coaches])

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_athlete_list(request):
    athletes = User.objects.filter(client_profile__isnull=False)
    return Response([{
        "id": u.id, "first_name": u.first_name, "last_name": u.last_name,
        "name": f"{u.first_name} {u.last_name}", "email": u.email,
        "status": "Active" if u.is_active else "Inactive"
    } for u in athletes])

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_delete_athlete(request, pk):
    User.objects.filter(id=pk, client_profile__isnull=False).delete()
    return Response({"message": "Supprimé"})

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_force_logout(request, pk):
    # Pour l'instant, on retourne un succès simple. 
    # (L'invalidation réelle nécessite la table de blacklistage JWT)
    return Response({"message": "Déconnecté"})