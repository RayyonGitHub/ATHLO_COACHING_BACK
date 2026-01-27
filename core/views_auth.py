from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Coach

@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Inscription d'un nouvel utilisateur"""
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        full_name = request.data.get('fullName', '')
        role = request.data.get('role', 'athlete')
        
        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)
        
        if User.objects.filter(email=email).exists():
            return Response({'message': 'Un compte avec cet email existe déjà'}, status=400)
        
        if User.objects.filter(username=email).exists():
            return Response({'message': 'Un compte avec cet email existe déjà'}, status=400)
        
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        if role == 'coach':
            Coach.objects.create(user=user)
        
        return Response({
            'message': 'Inscription réussie',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': full_name,
                'role': role
            }
        }, status=201)
        
    except Exception as e:
        return Response({'message': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Connexion personnalisée"""
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)
        
        user = User.objects.filter(email=email).first()
        
        if not user or not user.check_password(password):
            return Response({'message': 'Email ou mot de passe incorrect'}, status=401)
        
        refresh = RefreshToken.for_user(user)
        role = 'coach' if hasattr(user, 'coach_profile') else 'athlete'
        
        return Response({
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}".strip(),
                'role': role
            }
        })
        
    except Exception as e:
        return Response({'message': str(e)}, status=500)