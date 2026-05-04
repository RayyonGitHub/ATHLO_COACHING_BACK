from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Coach, Client, Programme, Salle, Devis, ClientInvitation, Commande, Facture
from .serializers_prospect import (
    PublicCoachSerializer,
    ProspectActivateAthleteSerializer,
    ProspectDevisCreateSerializer,
    InvitationCheckoutPaySerializer,
    InvitationSetPasswordSerializer,
)
from .serializers import SalleSerializer, DevisSerializer
from core.views import calcul_distance


CHECKOUT_SIGNER_SALT = "athlo-prospect-checkout-v1"
CHECKOUT_TOKEN_MAX_AGE = 60 * 60 * 3  # 3h


def _normalize_offres(raw_offres):
    defaults = {
        "seance": 60,
        "pack": 500,
        "abonnement": 180,
    }

    if not isinstance(raw_offres, dict):
        return defaults

    normalized = defaults.copy()

    for key in normalized.keys():
        value = raw_offres.get(key, normalized[key])
        try:
            normalized[key] = float(value)
        except (TypeError, ValueError):
            normalized[key] = defaults[key]

    return normalized


def _get_specialites(coach):
    specialites = []

    if isinstance(coach.specialites_tags, list):
        specialites.extend([str(tag).strip() for tag in coach.specialites_tags if str(tag).strip()])

    if coach.specialite and coach.specialite.strip() and coach.specialite.strip() not in specialites:
        specialites.append(coach.specialite.strip())

    return specialites


def _get_public_programmes(coach):
    programmes = Programme.objects.filter(coach=coach).order_by('-id')[:2]
    result = []

    for programme in programmes:
        result.append({
            "id": programme.id,
            "titre": programme.titre,
            "duree": f"{programme.seances.count()} séance(s)"
        })

    return result


def _serialize_public_coach(coach):
    offres = _normalize_offres(coach.offres_tarifs)
    moyenne_note = coach.avis.aggregate(avg=Avg('note'))['avg'] or 0
    avis_count = coach.avis.count()

    prenom = coach.user.first_name or ""
    nom = coach.user.last_name or coach.user.username or coach.user.email
    full_name = f"{prenom} {nom}".strip()

    payload = {
        "id": coach.id,
        "nom": nom,
        "prenom": prenom,
        "full_name": full_name,
        "ville": coach.ville or "",
        "specialites": _get_specialites(coach),
        "note": round(float(moyenne_note), 1) if moyenne_note else 0.0,
        "avis": avis_count,
        "tarifs": offres,
        "programmes_gratuits": _get_public_programmes(coach),
        "image": None,
    }

    return PublicCoachSerializer(payload).data


def _get_default_offer_for_invitation(coach):
    offres = _normalize_offres(coach.offres_tarifs)

    if float(offres.get('abonnement', 0)) > 0:
        return ('abonnement', 'Abonnement mensuel', float(offres['abonnement']))

    if float(offres.get('pack', 0)) > 0:
        return ('pack', 'Pack 10 séances', float(offres['pack']))

    return ('seance', 'Séance unique', float(offres['seance']))


def _send_email(subject, message, recipient):
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', settings.EMAIL_HOST_USER),
        recipient_list=[recipient],
        fail_silently=False,
    )


def _get_valid_invitation_or_response(token):
    invitation = ClientInvitation.objects.select_related('coach__user', 'client__user').filter(token=token).first()

    if not invitation:
        return None, Response({"message": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if invitation.status == 'activated':
        return None, Response({"message": "Cette invitation a déjà été utilisée."}, status=status.HTTP_400_BAD_REQUEST)

    if invitation.status == 'cancelled':
        return None, Response({"message": "Cette invitation a été annulée."}, status=status.HTTP_400_BAD_REQUEST)

    if invitation.is_expired():
        if invitation.status != 'expired':
            invitation.status = 'expired'
            invitation.save(update_fields=['status'])
        return None, Response({"message": "Cette invitation a expiré."}, status=status.HTTP_400_BAD_REQUEST)

    return invitation, None


class PublicCoachListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ville = (request.query_params.get('ville') or '').strip().lower()
        specialite = (request.query_params.get('specialite') or '').strip().lower()
        note_min = request.query_params.get('note_min')
        prix_max = request.query_params.get('prix_max')
        type_offre = (request.query_params.get('type_offre') or 'tous').strip().lower()

        coaches = Coach.objects.select_related('user').prefetch_related('avis', 'programmes_crees').all()

        results = []
        for coach in coaches:
            serialized = _serialize_public_coach(coach)

            if ville and ville not in (serialized.get('ville') or '').lower():
                continue

            if specialite:
                coach_specs = [s.lower() for s in serialized.get('specialites', [])]
                if specialite not in coach_specs:
                    continue

            if note_min:
                try:
                    if float(serialized['note']) < float(note_min):
                        continue
                except (TypeError, ValueError):
                    pass

            if prix_max:
                try:
                    max_price = float(prix_max)
                    if type_offre in ['seance', 'pack', 'abonnement']:
                        if float(serialized['tarifs'].get(type_offre, 999999)) > max_price:
                            continue
                    else:
                        cheapest = min(float(v) for v in serialized['tarifs'].values())
                        if cheapest > max_price:
                            continue
                except (TypeError, ValueError):
                    pass

            results.append(serialized)

        results.sort(key=lambda c: (-c['note'], -c['avis'], c['full_name']))
        return Response(results, status=status.HTTP_200_OK)


class ProspectCheckoutPayView(APIView):
    permission_classes = [IsAuthenticated]

    OFFER_LABELS = {
        'seance': 'Séance unique',
        'pack': 'Pack 10 séances',
        'abonnement': 'Abonnement mensuel',
    }

    def post(self, request):
        user = request.user

        if hasattr(user, 'coach_profile'):
            return Response(
                {"message": "Un coach ne peut pas utiliser ce tunnel prospect."},
                status=status.HTTP_403_FORBIDDEN
            )

        coach_id = request.data.get('coach_id')
        offer_type = (request.data.get('offer_type') or '').strip().lower()

        if offer_type not in ['seance', 'pack', 'abonnement']:
            return Response({"message": "Type d'offre invalide."}, status=status.HTTP_400_BAD_REQUEST)

        coach = get_object_or_404(Coach.objects.select_related('user'), id=coach_id)
        offres = _normalize_offres(coach.offres_tarifs)
        amount = offres.get(offer_type)

        card_number = ''.join(ch for ch in str(request.data.get('card_number', '')) if ch.isdigit())
        cardholder_name = (request.data.get('cardholder_name') or '').strip()
        email = (request.data.get('email') or user.email or '').strip()
        phone = (request.data.get('phone') or '').strip()

        if not card_number or len(card_number) < 12:
            return Response({"message": "Numéro de carte invalide."}, status=status.HTTP_400_BAD_REQUEST)

        if not cardholder_name:
            return Response({"message": "Nom du porteur requis."}, status=status.HTTP_400_BAD_REQUEST)

        payment_status = 'failed' if card_number.endswith('0002') or str(request.data.get('cvc', '')).strip() == '000' else 'success'

        token_payload = {
            "user_id": user.id,
            "coach_id": coach.id,
            "offer_type": offer_type,
            "offer_label": self.OFFER_LABELS[offer_type],
            "amount": amount,
            "email": email,
            "phone": phone,
            "payment_status": payment_status,
            "card_last4": card_number[-4:],
        }

        checkout_token = signing.dumps(token_payload, salt=CHECKOUT_SIGNER_SALT)

        return Response({
            "payment_status": payment_status,
            "checkout_token": checkout_token,
            "coach": _serialize_public_coach(coach),
            "offer": {
                "type": offer_type,
                "label": self.OFFER_LABELS[offer_type],
                "price": amount,
            },
            "message": "Paiement accepté." if payment_status == 'success' else "Paiement refusé.",
        }, status=status.HTTP_200_OK)


class ProspectCheckoutPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({"message": "Token manquant."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = signing.loads(token, salt=CHECKOUT_SIGNER_SALT, max_age=CHECKOUT_TOKEN_MAX_AGE)
        except SignatureExpired:
            return Response({"message": "Session de paiement expirée."}, status=status.HTTP_400_BAD_REQUEST)
        except BadSignature:
            return Response({"message": "Session de paiement invalide."}, status=status.HTTP_400_BAD_REQUEST)

        if payload.get("user_id") != request.user.id:
            return Response({"message": "Accès refusé à cette session."}, status=status.HTTP_403_FORBIDDEN)

        coach = get_object_or_404(Coach.objects.select_related('user'), id=payload.get("coach_id"))

        return Response({
            "payment_status": payload.get("payment_status"),
            "coach": _serialize_public_coach(coach),
            "offer": {
                "type": payload.get("offer_type"),
                "label": payload.get("offer_label"),
                "price": payload.get("amount"),
            },
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "card_last4": payload.get("card_last4"),
        }, status=status.HTTP_200_OK)


class ProspectActivateAthleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if hasattr(user, 'coach_profile'):
            return Response(
                {"message": "Un coach ne peut pas être converti via ce tunnel."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ProspectActivateAthleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payload = signing.loads(
                data['checkout_token'],
                salt=CHECKOUT_SIGNER_SALT,
                max_age=CHECKOUT_TOKEN_MAX_AGE
            )
        except SignatureExpired:
            return Response({"message": "Session de paiement expirée."}, status=status.HTTP_400_BAD_REQUEST)
        except BadSignature:
            return Response({"message": "Session de paiement invalide."}, status=status.HTTP_400_BAD_REQUEST)

        if payload.get("user_id") != user.id:
            return Response({"message": "Session de paiement non autorisée."}, status=status.HTTP_403_FORBIDDEN)

        if payload.get("payment_status") != "success":
            return Response({"message": "Le paiement n'est pas validé."}, status=status.HTTP_400_BAD_REQUEST)

        coach = get_object_or_404(Coach, id=payload.get("coach_id"))

        user.first_name = data['prenom']
        user.last_name = data['nom']
        user.email = user.email or payload.get("email") or user.email
        user.username = user.email
        user.save()

        athlete_profile, created = Client.objects.get_or_create(
            user=user,
            defaults={
                "coach": coach,
                "prenom": data['prenom'],
                "nom": data['nom'],
                "email": user.email,
                "telephone": data.get('telephone', ''),
                "age": data.get('age'),
                "taille": data.get('taille'),
                "poids": data.get('poids'),
                "genre": data.get('genre', 'M'),
                "niveau_activite": data.get('niveau_activite', '1.55'),
                "poids_cible": data.get('poids_cible'),
                "type_entrainement": data.get('type_entrainement', 'Musculation'),
                "objectifs_sportifs": data.get('objectifs_sportifs', ''),
                "pathologies_blessures": data.get('pathologies_blessures', ''),
                "consentement_rgpd": data.get('consentement_rgpd', True),
            }
        )
        
        if not created:
            athlete_profile.coach = coach
            athlete_profile.prenom = data['prenom']
            athlete_profile.nom = data['nom']
            athlete_profile.email = user.email
            athlete_profile.telephone = data.get('telephone', '')
            athlete_profile.age = data.get('age')
            athlete_profile.taille = data.get('taille')
            athlete_profile.poids = data.get('poids')
            athlete_profile.genre = data.get('genre', 'M')
            athlete_profile.niveau_activite = data.get('niveau_activite', '1.55')
            athlete_profile.poids_cible = data.get('poids_cible')
            athlete_profile.type_entrainement = data.get('type_entrainement', 'Musculation')
            athlete_profile.objectifs_sportifs = data.get('objectifs_sportifs', '')
            athlete_profile.pathologies_blessures = data.get('pathologies_blessures', '')
            athlete_profile.consentement_rgpd = data.get('consentement_rgpd', True)
            athlete_profile.save()

        refresh = RefreshToken.for_user(user)
        montant_ttc = payload.get("amount", 0)
        commande = Commande.objects.create(
            client=athlete_profile,
            coach=coach,
            offre_label=payload.get("offer_label"),
            offre_type=payload.get("offer_type"),
            montant_ttc=montant_ttc,
            montant_ht=round(montant_ttc / 1.2, 2), # Calcul automatique du HT (TVA 20%)
            status='PAID'
        )

        # 2. Génération automatique de l'entrée Facture
        Facture.objects.create(commande=commande)

        # 3. Si c'est un pack, on crédite le solde de l'athlète
        if payload.get("offer_type") == 'pack':
            athlete_profile.seances_restantes = (athlete_profile.seances_restantes or 0) + 10
            athlete_profile.save()
            
        return Response({
            "message": "Paiement confirmé et profil athlète activé.",
            "token": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "name": f"{user.first_name} {user.last_name}".strip(),
                "role": "athlete"
            },
            "athlete": {
                "id": athlete_profile.id,
                "coach_id": coach.id
            }
        }, status=status.HTTP_200_OK)


# -------------------------------------------------
# NOUVEAU FLOW : CLIENT AJOUTÉ PAR LE COACH
# -------------------------------------------------
class InvitationCheckoutPreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token', '').strip()
        if not token:
            return Response({"message": "Token manquant."}, status=status.HTTP_400_BAD_REQUEST)

        invitation, error_response = _get_valid_invitation_or_response(token)
        if error_response:
            return error_response

        return Response({
            "coach": _serialize_public_coach(invitation.coach),
            "offer": {
                "type": invitation.offer_type,
                "label": invitation.offer_label,
                "price": invitation.amount,
            },
            "email": invitation.email,
            "phone": invitation.phone,
            "full_name": f"{invitation.client.prenom} {invitation.client.nom}".strip(),
            "status": invitation.status,
            "expires_at": invitation.expires_at,
        }, status=status.HTTP_200_OK)


class InvitationCheckoutPayView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InvitationCheckoutPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invitation, error_response = _get_valid_invitation_or_response(data['invitation_token'])
        if error_response:
            return error_response

        if invitation.status in ['paid', 'activated']:
            return Response(
                {"message": "Cette invitation a déjà été réglée."},
                status=status.HTTP_400_BAD_REQUEST
            )

        card_number = ''.join(ch for ch in str(data.get('card_number', '')) if ch.isdigit())
        cvc = str(data.get('cvc', '')).strip()

        if not card_number or len(card_number) < 12:
            return Response({"message": "Numéro de carte invalide."}, status=status.HTTP_400_BAD_REQUEST)

        payment_status = 'failed' if card_number.endswith('0002') or cvc == '000' else 'success'

        invitation.email = data['email']
        invitation.phone = data.get('phone', '')
        invitation.card_last4 = card_number[-4:]
        invitation.payment_status = payment_status

        if payment_status == 'success':
            invitation.status = 'paid'
            invitation.paid_at = timezone.now()

            client = invitation.client
            user = client.user

            client.email = data['email']
            client.telephone = data.get('phone', '')
            client.save(update_fields=['email', 'telephone'])

            user.email = data['email']
            user.username = data['email']
            user.save(update_fields=['email', 'username'])

            invitation.save(update_fields=[
                'email',
                'phone',
                'card_last4',
                'payment_status',
                'status',
                'paid_at',
            ])

            NotificationMessage = (
                f"Paiement confirmé pour {client.prenom} {client.nom} "
                f"({invitation.offer_label} - {invitation.amount:.2f} €)."
            )

            from .models import Notification
            Notification.objects.create(
                coach=invitation.coach,
                seance=None,
                type='PAIEMENT',
                message=NotificationMessage
            )

            set_password_link = f"{settings.FRONTEND_URL}/invite/set-password?token={invitation.token}"

            _send_email(
                subject="ATHLO - Paiement confirmé, activez votre compte",
                message=(
                    f"Bonjour {client.prenom},\n\n"
                    f"Votre paiement a bien été validé.\n\n"
                    f"Pour activer votre compte ATHLO et définir votre mot de passe, "
                    f"cliquez sur ce lien :\n{set_password_link}\n\n"
                    f"Ce lien vous permettra d'accéder ensuite à votre espace client.\n\n"
                    f"L'équipe ATHLO"
                ),
                recipient=invitation.email
            )

            return Response({
                "payment_status": "success",
                "message": "Paiement validé.",
                "activation_token": invitation.token,
                "coach": _serialize_public_coach(invitation.coach),
                "offer": {
                    "type": invitation.offer_type,
                    "label": invitation.offer_label,
                    "price": invitation.amount,
                },
            }, status=status.HTTP_200_OK)

        invitation.save(update_fields=[
            'email',
            'phone',
            'card_last4',
            'payment_status',
        ])

        return Response({
            "payment_status": "failed",
            "message": "Paiement refusé.",
        }, status=status.HTTP_200_OK)


class InvitationSetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InvitationSetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invitation, error_response = _get_valid_invitation_or_response(data['token'])
        if error_response:
            return error_response

        if invitation.status != 'paid':
            return Response(
                {"message": "Le paiement doit être validé avant de définir le mot de passe."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = invitation.client.user

        try:
            validate_password(data['new_password'], user=user)
        except Exception as validation_error:
            messages = getattr(validation_error, 'messages', None)
            return Response({
                "message": messages[0] if messages else "Mot de passe invalide."
            }, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data['new_password'])
        user.save()

        invitation.status = 'activated'
        invitation.activated_at = timezone.now()
        invitation.save(update_fields=['status', 'activated_at'])

        _send_email(
            subject="ATHLO - Votre compte est prêt",
            message=(
                f"Bonjour {invitation.client.prenom},\n\n"
                f"Votre compte ATHLO est maintenant activé.\n\n"
                f"Vous pouvez vous connecter avec :\n"
                f"Email : {user.email}\n"
                f"Connexion : {settings.FRONTEND_URL}/login\n\n"
                f"L'équipe ATHLO"
            ),
            recipient=user.email
        )

        return Response({
            "message": "Compte activé avec succès."
        }, status=status.HTTP_200_OK)


class PublicSalleListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        rayon = request.query_params.get('rayon', 10)

        salles = Salle.objects.all()
        results = []

        for salle in salles:
            distance = None

            if lat and lng and salle.latitude is not None and salle.longitude is not None:
                distance = calcul_distance(
                    float(lat),
                    float(lng),
                    float(salle.latitude),
                    float(salle.longitude),
                )

                if distance > float(rayon):
                    continue

            results.append({
                "id": salle.id,
                "nom": salle.nom,
                "adresse": salle.adresse,
                "ville": salle.ville,
                "distance_km": round(distance, 2) if distance is not None else None,
            })

        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 999999)

        return Response(results, status=status.HTTP_200_OK)


class ProspectDemandeDevisView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        email = (request.query_params.get('email') or '').strip()

        if not email:
            return Response(
                {"message": "Email manquant pour récupérer l'historique."},
                status=status.HTTP_400_BAD_REQUEST
            )

        devis = Devis.objects.filter(email__iexact=email).select_related('coach__user').order_by('-id')
        serializer = DevisSerializer(devis, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProspectDevisCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        coach = get_object_or_404(Coach, id=data['coach_id'])

        devis = Devis.objects.create(
            coach=coach,
            nom=data['nom'],
            prenom=data['prenom'],
            email=data['email'],
            telephone=data.get('telephone', ''),
            age=data.get('age'),
            taille=data.get('taille'),
            poids=data.get('poids'),
            niveau_activite=data.get('niveauActivite', ''),
            type_entrainement=data.get('typeEntrainement', ''),
            objectif_sportif=data.get('objectifSportif', ''),
            budget=data.get('budget', ''),
            pathologies_blessures=data.get('pathologiesBlessures', ''),
            message=data.get('message', ''),
        )

        return Response(
            {
                "message": "Demande de devis envoyée avec succès.",
                "id": devis.id,
                "statut": devis.statut,
            },
            status=status.HTTP_201_CREATED
        )