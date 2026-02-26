from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

# ==========================================
# 1. LOGIN SÉCURISÉ POUR LE SUPER-ADMIN
# ==========================================
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login_view(request):
    """Connexion exclusive pour la page /admin-login"""
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)
        
        user = User.objects.filter(email=email).first()
        
        if not user or not user.check_password(password):
            return Response({'message': 'Identifiants incorrects'}, status=401)
            
        # BLOCAGE : Si ce n'est pas le staff, on le dégage.
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
                'role': 'admin' # Très important pour le Front
            }
        })
        
    except Exception as e:
        return Response({'message': str(e)}, status=500)


# ==========================================
# 2. GESTION DES COACHS
# ==========================================
@api_view(['GET'])
@permission_classes([IsAdminUser]) 
def admin_coach_list(request):
    """ Récupère la liste de tous les coachs """
    # Basé sur ton models.py (related_name='coach_profile')
    coach_users = User.objects.filter(coach_profile__isnull=False).order_by('-date_joined')
    
    data = []
    for user in coach_users:
        # Récupération de la spécialité depuis le JSONField si elle existe
        try:
            specialty = user.coach_profile.specialites_tags[0] if user.coach_profile.specialites_tags else "Général"
        except:
            specialty = "Général"

        data.append({
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "specialty": specialty,
            "date": user.date_joined.strftime("%b %d, %Y"),
            "status": "Validated" if user.is_active else "Suspended"
        })
        
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_toggle_coach_status(request, pk):
    """ Valider ou Bannir un coach """
    try:
        user = User.objects.get(id=pk, coach_profile__isnull=False)
        action = request.data.get('action') 
        
        if action == 'validate':
            user.is_active = True
        elif action == 'ban':
            user.is_active = False
        else:
            return Response({"error": "Action invalide"}, status=400)
            
        user.save()
        return Response({
            "message": "Statut mis à jour", 
            "status": "Validated" if user.is_active else "Suspended"
        })
        
    except User.DoesNotExist:
        return Response({"error": "Coach introuvable"}, status=404)