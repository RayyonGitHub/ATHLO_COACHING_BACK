from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.http import HttpResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .email_utils import send_html_email

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Coach
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Inscription d'un nouvel utilisateur"""
    try:
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password')
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        full_name = request.data.get('fullName', '')
        role = request.data.get('role', 'prospect')

        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)

        if User.objects.filter(email__iexact=email).exists():
            return Response({'message': 'Un compte avec cet email existe déjà'}, status=400)

        if User.objects.filter(username__iexact=email).exists():
            return Response({'message': 'Un compte avec cet email existe déjà'}, status=400)

        if not first_name and full_name:
            name_parts = full_name.strip().split(' ', 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''

        display_name = f"{first_name} {last_name}".strip() or full_name.strip() or email

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        if role == 'coach':
            Coach.objects.create(
                user=user,
                specialite=request.data.get('specialite', ''),
                ville=request.data.get('ville', ''),
                specialites_tags=request.data.get('specialites_tags', []),
                offres_tarifs=request.data.get('offres_tarifs', {}),
            )

        # Générer et renvoyer des tokens JWT pour garder l'utilisateur connecté
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Inscription réussie',
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'name': display_name,
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
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password')

        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)

        user = User.objects.filter(email__iexact=email).first()

        if not user or not user.check_password(password):
            return Response({'message': 'Email ou mot de passe incorrect'}, status=401)

        refresh = RefreshToken.for_user(user)
        role = 'prospect'
        if hasattr(user, 'coach_profile'):
            role = 'coach'
        elif hasattr(user, 'client_profile'):
            role = 'athlete'
        elif hasattr(user, 'responsable_profile'): # AJOUTEZ CECI
            role = 'responsable'
        elif hasattr(user, 'prospect_profile'): # Ou votre logique actuelle pour prospect
            role = 'prospect'

        return Response({
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'name': f"{user.first_name} {user.last_name}".strip(),
                'role': role
            }
        })

    except Exception as e:
        return Response({'message': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_view(request):
    """
    Envoie un lien de réinitialisation.
    Réponse volontairement générique pour éviter de révéler si l'email existe.
    """
    try:
        email = request.data.get('email', '').strip().lower()

        if not email:
            return Response({'message': 'Adresse email requise'}, status=400)

        user = User.objects.filter(email__iexact=email).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            platform = request.data.get("platform", "web")

            if platform == "mobile":
                backend_url = request.build_absolute_uri("/").rstrip("/")
                reset_link = f"{backend_url}/api/auth/reset-relay/?uid={uid}&token={token}"
            else:
                reset_link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

            send_html_email(
                subject="Réinitialisation de votre mot de passe ATHLO",
                to=user.email,
                greeting=f"Bonjour {user.first_name or user.username},",
                paragraphs=[
                    "Vous avez demandé la réinitialisation de votre mot de passe ATHLO.",
                    "Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe. "
                    "Ce lien est valable <strong>24 heures</strong>.",
                ],
                cta_label="Réinitialiser mon mot de passe",
                cta_url=reset_link,
                note="Si vous n'êtes pas à l'origine de cette demande, aucune action n'est requise.",
            )

        return Response({
            'message': "Si un compte existe avec cette adresse email, un lien de réinitialisation a été envoyé."
        }, status=200)

    except Exception as e:
        return Response({'message': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_view(request):
    """
    Réinitialise le mot de passe à partir du uid + token.
    """
    try:
        uid = request.data.get('uid', '').strip()
        token = request.data.get('token', '').strip()
        new_password = request.data.get('new_password', '')
        confirm_password = request.data.get('confirm_password', '')

        if not uid or not token:
            return Response({'message': 'Lien de réinitialisation invalide.'}, status=400)

        if not new_password or not confirm_password:
            return Response({'message': 'Tous les champs sont requis.'}, status=400)

        if new_password != confirm_password:
            return Response({'message': 'Les mots de passe ne correspondent pas.'}, status=400)

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except Exception:
            return Response({'message': 'Lien de réinitialisation invalide.'}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({'message': 'Le lien est invalide ou expiré.'}, status=400)

        try:
            validate_password(new_password, user=user)
        except Exception as validation_error:
            messages = getattr(validation_error, 'messages', None)
            return Response({
                'message': messages[0] if messages else 'Mot de passe invalide.'
            }, status=400)

        user.set_password(new_password)
        user.save()

        return Response({'message': 'Mot de passe réinitialisé avec succès.'}, status=200)

    except Exception as e:
        return Response({'message': str(e)}, status=500)


def invite_relay(request):
    """
    Relay HTTP → deep link pour le flow invitation.
    Les clients email bloquent exp:// et athlo:// — on passe par cette URL HTTP.
    """
    token = request.GET.get("token", "")
    expo_dev_url = getattr(settings, "EXPO_DEV_URL", None)
    if expo_dev_url:
        target = f"{expo_dev_url}/--/invite-checkout?token={token}"
    else:
        target = f"athlo://invite-checkout?token={token}"
    response = HttpResponse(status=302)
    response["Location"] = target
    return response


def password_reset_relay(request):
    """
    Relay HTTP → deep link pour le reset de mot de passe.
    Les clients email bloquent exp:// et athlo:// — on passe par cette URL HTTP
    qui redirige vers le bon deep link côté app.
    """
    uid = request.GET.get("uid", "")
    token = request.GET.get("token", "")
    expo_dev_url = getattr(settings, "EXPO_DEV_URL", None)
    if expo_dev_url:
        target = f"{expo_dev_url}/--/reset-password?uid={uid}&token={token}"
    else:
        target = f"athlo://reset-password?uid={uid}&token={token}"
    response = HttpResponse(status=302)
    response["Location"] = target
    return response
