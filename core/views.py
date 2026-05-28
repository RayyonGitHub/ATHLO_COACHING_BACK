import random
import string
import datetime
import math
from datetime import timedelta
from collections import defaultdict
import re

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q, Sum, Min, Max, F
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from django.core.mail import send_mail
from .email_utils import link_for_platform, send_html_email
from django.conf import settings
from icalendar import Calendar, Event
from rest_framework import viewsets, status, generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework_simplejwt.tokens import RefreshToken


from .models import (
    Client, Coach, Exercice, Programme, Seance,
    SeanceExercice, Performance, Indisponibilite,
    Inscription, Notification, NotificationAthlete, Salle, Avis,
    ClientInvitation, Devis, Commande, LigneCommande, Produit, ContratAthlete
)
from .serializers import (
    ClientSerializer, CoachSerializer, ExerciceSerializer,
    ProgrammeSerializer, SeanceSerializer, PerformanceSerializer,
    IndisponibiliteSerializer, NotificationSerializer,
    NotificationAthleteSerializer, SalleSerializer, AvisSerializer,
    ProspectCoachListSerializer, ProspectCoachDetailSerializer, DevisSerializer, CommandeSerializer
)


VILLE_COORDS = {
    "Aix-en-Provence": (43.5297, 5.4474),
    "Amiens": (49.8941, 2.2958),
    "Angers": (47.4784, -0.5632),
    "Annecy": (45.8992, 6.1294),
    "Avignon": (43.9493, 4.8055),
    "Bayonne": (43.4929, -1.4748),
    "Belfort": (47.6386, 6.8638),
    "Besançon": (47.2378, 6.0241),
    "Bordeaux": (44.8378, -0.5792),
    "Boulogne-Billancourt": (48.8397, 2.2399),
    "Brest": (48.3904, -4.4861),
    "Caen": (49.1829, -0.3707),
    "Clermont-Ferrand": (45.7772, 3.0870),
    "Dijon": (47.3220, 5.0415),
    "Grenoble": (45.1885, 5.7245),
    "Le Havre": (49.4944, 0.1079),
    "Le Mans": (48.0061, 0.1996),
    "Lille": (50.6292, 3.0573),
    "Limoges": (45.8336, 1.2611),
    "Lyon": (45.7640, 4.8357),
    "Marseille": (43.2965, 5.3698),
    "Metz": (49.1193, 6.1757),
    "Montpellier": (43.6110, 3.8767),
    "Mulhouse": (47.7508, 7.3359),
    "Nancy": (48.6921, 6.1844),
    "Nantes": (47.2184, -1.5536),
    "Nice": (43.7102, 7.2620),
    "Nîmes": (43.8367, 4.3601),
    "Orléans": (47.9029, 1.9093),
    "Paris": (48.8566, 2.3522),
    "Perpignan": (42.6887, 2.8948),
    "Poitiers": (46.5802, 0.3404),
    "Reims": (49.2583, 4.0317),
    "Rennes": (48.1173, -1.6778),
    "Rouen": (49.4431, 1.0993),
    "Saint-Étienne": (45.4397, 4.3872),
    "Strasbourg": (48.5734, 7.7521),
    "Toulon": (43.1242, 5.9280),
    "Toulouse": (43.6047, 1.4442),
    "Tours": (47.3941, 0.6848),
    "Villeurbanne": (45.7660, 4.8795),
}


def calcul_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _consume_seance_credit(client):
    if client.seances_restantes <= 0:
        raise ValidationError({"erreur": "Quota de séances atteint pour cet athlète."})
    client.seances_restantes = F('seances_restantes') - 1
    client.save(update_fields=['seances_restantes'])
    client.refresh_from_db(fields=['seances_restantes'])


def _restore_seance_credit(client):
    client.seances_restantes = F('seances_restantes') + 1
    client.save(update_fields=['seances_restantes'])
    client.refresh_from_db(fields=['seances_restantes'])


def _consume_seance_credit(client):
    if client.abonnement_valide:
        return
    active_contract = client.contrats.select_for_update().filter(
        statut='ACTIF',
        type_contrat__in=['PACK', 'UNITE'],
        seances_restantes__gt=0
    ).order_by('date_debut', 'id').first()
    if not active_contract:
        raise ValidationError({"erreur": "Quota de seances atteint pour cet athlete."})
    active_contract.seances_restantes = F('seances_restantes') - 1
    active_contract.save(update_fields=['seances_restantes'])
    active_contract.refresh_from_db(fields=['seances_restantes'])
    if active_contract.seances_restantes <= 0:
        active_contract.statut = 'EXPIRE'
        active_contract.save(update_fields=['statut'])
    client.seances_restantes = F('seances_restantes') - 1
    client.save(update_fields=['seances_restantes'])
    client.refresh_from_db(fields=['seances_restantes'])


def _restore_seance_credit(client):
    active_contract = client.contrats.filter(type_contrat__in=['PACK', 'UNITE']).order_by('-date_debut', '-id').first()
    if active_contract:
        active_contract.seances_restantes = F('seances_restantes') + 1
        active_contract.statut = 'ACTIF'
        active_contract.save(update_fields=['seances_restantes', 'statut'])
    client.seances_restantes = F('seances_restantes') + 1
    client.save(update_fields=['seances_restantes'])
    client.refresh_from_db(fields=['seances_restantes'])


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not user.check_password(old_password):
            return Response({"error": "Ancien mot de passe incorrect."}, status=400)

        if len(new_password) < 8:
            return Response({"error": "8 caractères minimum."}, status=400)

        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)
        return Response({"message": "Mot de passe modifié avec succès !"})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        found_user = User.objects.filter(email__iexact=email).first()
        user = authenticate(
            username=found_user.username if found_user else email,
            password=request.data.get("password")
        )
        if not user:
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)
        role = 'coach' if hasattr(user, 'coach_profile') else 'athlete' if hasattr(user, 'client_profile') else 'prospect'

        return Response({
            "token": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "role": role
            }
        })


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def _get_default_offer_for_invitation(self, coach):
        raw_offres = coach.offres_tarifs if isinstance(coach.offres_tarifs, dict) else {}

        try:
            abonnement = float(raw_offres.get('abonnement', 0) or 0)
        except (TypeError, ValueError):
            abonnement = 0

        try:
            pack = float(raw_offres.get('pack', 0) or 0)
        except (TypeError, ValueError):
            pack = 0

        try:
            seance = float(raw_offres.get('seance', 60) or 60)
        except (TypeError, ValueError):
            seance = 60

        if abonnement > 0:
            return ('abonnement', 'Abonnement mensuel', abonnement)
        if pack > 0:
            return ('pack', 'Pack 10 séances', pack)
        return ('seance', 'Séance unique', seance)

    @transaction.atomic
    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'coach_profile'):
            raise PermissionDenied("Seul un coach peut ajouter un client.")

        coach_profile = self.request.user.coach_profile
        email = serializer.validated_data.get('email')
        prenom = serializer.validated_data.get('prenom', '')
        nom = serializer.validated_data.get('nom', '')
        telephone = serializer.validated_data.get('telephone', '')

        if not email:
            raise ValidationError({"email": "L'email est obligatoire."})

        if User.objects.filter(email=email).exists():
            raise ValidationError({"email": "Un utilisateur avec cet email existe déjà."})

        if User.objects.filter(username=email).exists():
            raise ValidationError({"email": "Un utilisateur avec cet email existe déjà."})

        user = User.objects.create(
            username=email,
            email=email,
            first_name=prenom,
            last_name=nom,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()

        client = serializer.save(coach=coach_profile, user=user)

        # ------------------------------------------------------------------
        # --- NOUVELLE LOGIQUE : CHOIX DU TARIF DEPUIS LE FRONTEND ---
        # ------------------------------------------------------------------
        selected_offer_type = self.request.data.get('offer_type')
        raw_offres = coach_profile.offres_tarifs if isinstance(coach_profile.offres_tarifs, dict) else {}

        OFFER_LABELS = {
            'abonnement': 'Abonnement mensuel',
            'pack': 'Pack 10 séances',
            'seance': 'Séance unique',
        }

        if selected_offer_type in OFFER_LABELS:
            offer_type = selected_offer_type
            offer_label = OFFER_LABELS[selected_offer_type]
            amount = float(raw_offres.get(selected_offer_type, 0) or 0)
        else:
            offer_type, offer_label, amount = self._get_default_offer_for_invitation(coach_profile)

        # Allow frontend to override the amount (custom pricing per client)
        custom_amount = self.request.data.get('amount')
        if custom_amount is not None:
            try:
                parsed = float(custom_amount)
                if parsed > 0:
                    amount = parsed
            except (TypeError, ValueError):
                pass
        # ------------------------------------------------------------------

        invitation = ClientInvitation.objects.create(
            coach=coach_profile,
            client=client,
            email=email,
            phone=telephone,
            offer_type=offer_type,
            offer_label=offer_label,
            amount=amount,
            expires_at=timezone.now() + timedelta(days=7),
        )

        platform = self.request.data.get("platform", "web")
        if platform == "mobile":
            backend_url = self.request.build_absolute_uri("/").rstrip("/")
            invite_link = f"{backend_url}/api/auth/invite-relay/?token={invitation.token}"
        else:
            invite_link = f"{settings.FRONTEND_URL}/invite/checkout?token={invitation.token}"
        expiry_str = invitation.expires_at.strftime("%d/%m/%Y à %H:%M")
        coach_name = f"{coach_profile.user.first_name} {coach_profile.user.last_name}".strip()

        send_html_email(
            subject="ATHLO — Finalisez votre inscription",
            to=email,
            greeting=f"Bonjour {prenom or nom or 'Athlète'},",
            paragraphs=[
                f"Votre coach <strong>{coach_name}</strong> vous a invité à rejoindre ATHLO.",
                f"Pour activer votre compte, finalisez votre paiement pour l'offre "
                f"<strong>{offer_label}</strong> — <strong>{amount}€</strong>.",
                f"Une fois le paiement validé, vous pourrez définir votre mot de passe "
                f"et accéder à votre espace personnel.",
                f"Cette invitation expire le <strong>{expiry_str}</strong>.",
            ],
            cta_label="Finaliser mon inscription",
            cta_url=invite_link,
        )

        Notification.objects.create(
            coach=coach_profile,
            seance=None,
            type='INFO',
            message=f"Invitation de paiement envoyée à {prenom} {nom} ({email}) pour {offer_label} ({amount}€)."
        )


class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Ne pas créer automatiquement de profil Coach pour tout utilisateur authentifié.
        # Retourne le profil coach si existant, sinon 404 pour éviter la pollution des users.
        coach = getattr(request.user, 'coach_profile', None)
        if not coach:
            return Response({"detail": "Profil coach introuvable."}, status=404)
        data = CoachSerializer(coach).data
        data['prenom'] = request.user.first_name
        data['nom'] = request.user.last_name
        data['email'] = request.user.email
        return Response(data)

    def patch(self, request):
        user = request.user
        # Met à jour le profil coach uniquement si le profil existe
        coach = getattr(user, 'coach_profile', None)
        if not coach:
            return Response({"detail": "Profil coach introuvable."}, status=404)

        if 'prenom' in request.data:
            user.first_name = request.data.get('prenom')
        if 'nom' in request.data:
            user.last_name = request.data.get('nom')
        if 'email' in request.data:
            user.email = request.data.get('email')
            user.username = request.data.get('email')

        user.save()

        serializer = CoachSerializer(coach, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


class CoachAvailableSallesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coach = getattr(request.user, 'coach_profile', None)
        if not coach:
            return Response({"error": "Profil coach introuvable."}, status=403)

        ville_coach = (coach.ville or '').strip()
        ville_query = (request.query_params.get('ville') or '').strip()

        # Règle métier:
        # - Si le coach a une ville, on force ce filtre côté back.
        # - Sinon, on n'affiche que les salles de la ville recherchée (si fournie).
        salles_qs = Salle.objects.all().order_by('nom')
        if ville_coach:
            salles_qs = salles_qs.filter(ville__iexact=ville_coach)
        elif ville_query:
            salles_qs = salles_qs.filter(ville__icontains=ville_query)
        else:
            salles_qs = Salle.objects.none()

        return Response([
            {
                "id": s.id,
                "nom": s.nom,
                "adresse": s.adresse,
                "ville": s.ville,
            }
            for s in salles_qs
        ])


class CoachDevisListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coach = getattr(request.user, 'coach_profile', None)
        if not coach:
            return Response({"error": "Accès réservé aux coachs."}, status=403)

        devis_qs = Devis.objects.filter(coach=coach).select_related('coach__user', 'invitation_liee').order_by('-date_creation')
        return Response(DevisSerializer(devis_qs, many=True).data, status=200)


class CoachTraiterDevisView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, devis_id):
        coach = getattr(request.user, 'coach_profile', None)
        if not coach:
            return Response({"error": "Accès réservé aux coachs."}, status=403)

        action_value = (request.data.get('action') or '').strip().lower()
        if action_value not in ('accepter', 'refuser'):
            return Response({"error": "Action invalide. Utilisez 'accepter' ou 'refuser'."}, status=400)

        nouveau_statut = 'accepte' if action_value == 'accepter' else 'refuse'

        devis = get_object_or_404(Devis.objects.select_related('coach', 'coach__user', 'prospect'), id=devis_id, coach=coach)
        if devis.statut in ('accepte', 'refuse'):
            return Response({"error": "Ce devis a déjà été traité."}, status=400)

        update_fields = ['statut']
        devis.statut = nouveau_statut
        if nouveau_statut == 'accepte':
            if not devis.prix_propose or devis.prix_propose <= 0:
                return Response({"error": "Ce devis n'a pas de prix proposé par le prospect."}, status=400)

        devis.save(update_fields=update_fields)

        return Response(
            {
                "message": "Devis traité avec succès.",
                "devis_id": devis.id,
                "devis_statut": devis.statut,
                "prix_propose": devis.prix_propose,
                "devis": DevisSerializer(devis).data,
            },
            status=200,
        )


class AthleteMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        athlete_profile, _ = Client.objects.get_or_create(user=request.user)
        return Response(ClientSerializer(athlete_profile).data)

    def patch(self, request):
        user = request.user
        athlete_profile, _ = Client.objects.get_or_create(user=user)

        if 'prenom' in request.data:
            user.first_name = request.data.get('prenom')
        if 'nom' in request.data:
            user.last_name = request.data.get('nom')
        if 'email' in request.data:
            user.email = request.data.get('email')
            user.username = request.data.get('email')

        user.save()

        serializer = ClientSerializer(athlete_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


class ProspectMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'email': user.email,
            'prenom': user.first_name,
            'nom': user.last_name,
            'role': 'prospect'
        })

    def patch(self, request):
        user = request.user

        if 'prenom' in request.data:
            user.first_name = request.data.get('prenom')
        if 'nom' in request.data:
            user.last_name = request.data.get('nom')
        if 'email' in request.data:
            user.email = request.data.get('email')
            user.username = request.data.get('email')

        user.save()

        athlete_profile, created = Client.objects.get_or_create(user=user)

        serializer = ClientSerializer(athlete_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profil complété avec succès',
                'athlete': serializer.data,
                'role': 'athlete'
            })

        return Response(serializer.errors, status=400)


class ExerciceViewSet(viewsets.ModelViewSet):
    queryset = Exercice.objects.all()
    serializer_class = ExerciceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ['categorie']


class ProgrammeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgrammeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Programme.objects.filter(coach=user.coach_profile)
        if hasattr(user, 'client_profile'):
            return Programme.objects.filter(athlete=user.client_profile)
        return Programme.objects.none()

    def perform_create(self, serializer):
        coach = getattr(self.request.user, 'coach_profile', None)
        if not coach:
            raise ValidationError({"error": "Profil coach introuvable. Action refusée."})
        athlete = serializer.validated_data.get('athlete')
        if not athlete:
            raise ValidationError({"athlete": "Vous devez assigner ce programme à un athlète."})
        if athlete.coach_id != coach.id:
            raise ValidationError({"athlete": "Cet athlète n'appartient pas à votre portefeuille."})

        programme = serializer.save(coach=coach)

        try:
            athlete_obj = getattr(programme, 'athlete', None)
            if athlete_obj:
                NotificationAthlete.objects.create(
                    client=athlete_obj,
                    message=f"Nouveau programme : {programme.titre}",
                    type='SEANCE'
                )
        except Exception as e:
            print(f"⚠️ Erreur notification (mais programme créé) : {e}")


class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    permission_classes = [IsAuthenticated]

    def _inject_salle_from_alias(self, data):
        """Accept both 'salle' and 'salle_id' payload formats from frontend."""
        if 'salle' not in data and 'salle_id' in data:
            data['salle'] = data.get('salle_id')

    def _pick_default_salle_for_coach(self, coach):
        if not coach:
            return None

        coach_salles = coach.salles.all()
        if coach_salles.count() == 1:
            return coach_salles.first()

        ville_coach = (coach.ville or '').strip()
        if ville_coach:
            salle_ville = coach_salles.filter(ville__iexact=ville_coach).first()
            if salle_ville:
                return salle_ville

        return None

    def get_queryset(self):
        user = self.request.user

        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(
                Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)
            ).distinct()

        if hasattr(user, 'client_profile'):
            athlete = user.client_profile
            coach_associe = athlete.coach

            q_mes_seances = Q(programme__athlete=athlete) | Q(inscriptions__client=athlete)
            q_collectives = Q(est_collective=True)
            q_indiv_vides = Q(est_collective=False, inscriptions__isnull=True, programme__isnull=True)

            return Seance.objects.filter(
                Q(coach=coach_associe) &
                (q_mes_seances | q_collectives | q_indiv_vides)
            ).distinct()

        return Seance.objects.none()

    def create(self, request, *args, **kwargs):
        try:
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            self._inject_salle_from_alias(data)
            exercices_data = data.pop('exercices', [])
            programme_id = data.get('programme')
            has_planning = bool(data.get('jour_prevu') or data.get('heure_debut') or data.get('heure_fin'))
            if programme_id and has_planning:
                programme = get_object_or_404(Programme, id=programme_id)
                athlete = getattr(programme, 'athlete', None)
                if athlete and not athlete.peut_reserver_seance:
                    return Response({"erreur": "Quota de séances atteint pour cet athlète."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(data=data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            self.perform_create(serializer)
            seance_creee = serializer.instance

            if exercices_data:
                for exo in exercices_data:
                    SeanceExercice.objects.create(
                        seance=seance_creee,
                        exercice_id=exo.get('exercice_id'),
                        series=exo.get('series', 3),
                        repetitions=exo.get('repetitions', '10'),
                        poids=exo.get('poids', 'Poids du corps'),
                        repos=exo.get('repos', '60s'),
                        ordre=exo.get('ordre', 1)
                    )

            jour_str = seance_creee.jour_prevu.strftime('%d/%m/%Y') if seance_creee.jour_prevu else 'à planifier'
            heure_str = seance_creee.heure_debut.strftime('%H:%M') if seance_creee.heure_debut else ''
            notif_message = f"Nouvelle séance : {seance_creee.titre} le {jour_str}"
            if heure_str:
                notif_message += f" à {heure_str}"

            if seance_creee.programme and seance_creee.programme.athlete:
                NotificationAthlete.objects.create(
                    client=seance_creee.programme.athlete,
                    message=notif_message,
                    type='SEANCE'
                )
            elif seance_creee.est_collective and seance_creee.coach:
                athletes = Client.objects.filter(coach=seance_creee.coach)
                NotificationAthlete.objects.bulk_create([
                    NotificationAthlete(client=a, message=notif_message, type='SEANCE')
                    for a in athletes
                ])

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except ValidationError as e:
            return Response({"erreur": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"erreur_interne": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_create(self, serializer):
        coach = getattr(self.request.user, 'coach_profile', None)
        salle = serializer.validated_data.get('salle')
        if salle is None:
            salle = self._pick_default_salle_for_coach(coach)
        serializer.save(coach=coach, salle=salle)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.programme and instance.programme.athlete:
            athlete = instance.programme.athlete
            NotificationAthlete.objects.create(
                client=athlete,
                message=f"Suppression : La séance '{instance.titre}' a été annulée.",
                type='SEANCE'
            )

        instance.inscriptions.all().delete()
        Notification.objects.create(
            coach=instance.coach,
            seance=None,
            type='ANNULATION',
            message=f"La séance '{instance.titre}' a été définitivement supprimée de l'agenda."
        )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            self._inject_salle_from_alias(data)
            exercices_data = data.pop('exercices', None)

            ancienne_date = instance.jour_prevu
            ancienne_heure = instance.heure_debut
            ancienne_heure_fin = instance.heure_fin
            etait_completee = instance.est_completee
            programme_athlete = instance.programme.athlete if instance.programme and instance.programme.athlete else None
            devient_planifiee = (
                programme_athlete
                and not ancienne_date
                and (data.get('jour_prevu') or data.get('heure_debut') or data.get('heure_fin'))
            )
            doit_creer_inscription_programme = (
                programme_athlete
                and not instance.inscriptions.filter(client=programme_athlete, statut__in=['CONFIRME', 'PRESENT', 'ABSENT']).exists()
                and (data.get('jour_prevu') or data.get('heure_debut') or data.get('heure_fin'))
            )

            if devient_planifiee and not programme_athlete.peut_reserver_seance:
                return Response({"erreur": "Quota de séances atteint pour cet athlète."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(instance, data=data, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            instance = serializer.save()

            if doit_creer_inscription_programme:
                Inscription.objects.create(seance=instance, client=programme_athlete, statut='CONFIRME')
                _consume_seance_credit(programme_athlete)

            if exercices_data is not None:
                SeanceExercice.objects.filter(seance=instance).delete()

                for exo in exercices_data:
                    SeanceExercice.objects.create(
                        seance=instance,
                        exercice_id=exo.get('exercice_id'),
                        series=exo.get('series', 3),
                        repetitions=exo.get('repetitions', '10'),
                        poids=exo.get('poids', 'Poids du corps'),
                        repos=exo.get('repos', '60s'),
                        ordre=exo.get('ordre', 1)
                    )

            date_ou_heure_modifiee = (
                ancienne_date != instance.jour_prevu or
                ancienne_heure != instance.heure_debut or
                ancienne_heure_fin != instance.heure_fin
            )

            if date_ou_heure_modifiee and instance.programme and instance.programme.athlete:
                athlete = instance.programme.athlete
                jour_str = instance.jour_prevu.strftime('%d/%m/%Y') if instance.jour_prevu else 'à planifier'
                heure_str = instance.heure_debut.strftime('%H:%M') if instance.heure_debut else ''

                message = f"Modification : {instance.titre} le {jour_str}"
                if heure_str:
                    message += f" à {heure_str}"

                NotificationAthlete.objects.create(
                    client=athlete,
                    message=message,
                    type='SEANCE'
                )

            if date_ou_heure_modifiee and instance.coach:
                jour_str = instance.jour_prevu.strftime('%d/%m/%Y') if instance.jour_prevu else 'à planifier'
                heure_str = instance.heure_debut.strftime('%H:%M') if instance.heure_debut else ''

                message = f"Modification horaires : {instance.titre} le {jour_str}"
                if heure_str:
                    message += f" à {heure_str}"

                Notification.objects.create(
                    coach=instance.coach,
                    seance=None,
                    type='MODIFICATION',
                    message=message
                )

            if not etait_completee and instance.est_completee and instance.coach:
                jour_str = instance.jour_prevu.strftime('%d/%m/%Y') if instance.jour_prevu else ''
                Notification.objects.create(
                    coach=instance.coach,
                    seance=instance,
                    type='MODIFICATION',
                    message=f"La séance '{instance.titre}' du {jour_str} a été marquée comme terminée. Bon travail !"
                )

            return Response(serializer.data)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"erreur_interne": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='resume')
    def get_resume(self, request, pk=None):
        seance = self.get_object()
        athlete = getattr(request.user, 'client_profile', None)

        if not athlete:
            return Response({"error": "Seul un athlète peut voir son résumé"}, status=400)

        perfs = Performance.objects.filter(
            client=athlete,
            seance_exercice__seance=seance
        ).select_related('seance_exercice__exercice').order_by('seance_exercice__ordre', 'id')

        resultats = []
        total_volume = 0

        for p in perfs:
            poids_str = str(p.poids_utilise).replace(',', '.')
            nombres = re.findall(r"[-+]?\d*\.\d+|\d+", poids_str)
            poids_num = float(nombres[0]) if nombres else 0.0

            vol_exo = poids_num * (p.reps_realisees or 0) * (p.series_realisees or 1)
            total_volume += vol_exo

            resultats.append({
                "id": p.id,
                "exercice_id": p.seance_exercice.exercice_id,
                "exercice": p.seance_exercice.exercice.nom,
                "muscle": p.seance_exercice.exercice.muscle_principal or p.seance_exercice.exercice.categorie or "Général",
                "series": p.series_realisees,
                "reps": p.reps_realisees,
                "poids": float(p.poids_utilise or 0),
                "volume_exercice": int(vol_exo)
            })

        return Response({
            "titre_seance": seance.titre,
            "date": seance.jour_prevu.strftime("%d/%m/%Y") if seance.jour_prevu else "Date libre",
            "exercices": resultats,
            "volume_total": int(total_volume),
            "ressenti": getattr(seance, 'ressenti_client', None),
            "notes": getattr(seance, 'notes_client', None)
        })


class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        athlete = getattr(request.user, 'client_profile', None)
        if not athlete:
            return Response({"error": "Profil athlete introuvable"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.localtime()
        today = now.date()
        current_time = now.time()

        seances_en_cours = Seance.objects.filter(
            Q(programme__athlete=athlete) | Q(inscriptions__client=athlete, inscriptions__statut='CONFIRME'),
            est_completee=False,
            jour_prevu__isnull=False,
            heure_fin__isnull=False
        ).distinct()

        for seance in seances_en_cours:
            if seance.jour_prevu < today or (seance.jour_prevu == today and seance.heure_fin < current_time):
                inscription, created = Inscription.objects.get_or_create(
                    seance=seance,
                    client=athlete,
                    defaults={'statut': 'ABSENT'}
                )
                if not created and inscription.statut != 'ABSENT':
                    inscription.statut = 'ABSENT'
                    inscription.save()

                if not seance.est_collective and seance.programme and seance.programme.athlete == athlete:
                    seance.est_completee = True
                    seance.save()

        coach_associe = athlete.coach
        q_mes_seances = Q(programme__athlete=athlete) | Q(inscriptions__client=athlete)
        q_collectives = Q(est_collective=True, coach=coach_associe) if coach_associe else Q(pk__in=[])
        q_indiv_vides = Q(est_collective=False, inscriptions__isnull=True, programme__isnull=True, coach=coach_associe) if coach_associe else Q(pk__in=[])

        prochaine_seance = Seance.objects.filter(
            q_mes_seances | q_collectives | q_indiv_vides,
            est_completee=False,
            jour_prevu__gte=today
        ).exclude(
            inscriptions__client=athlete, inscriptions__statut='ABSENT'
        ).distinct().order_by('jour_prevu', 'heure_debut', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            seance_data = SeanceSerializer(prochaine_seance, context={'request': request}).data

        random.seed(athlete.id + today.toordinal())
        pas_jour = random.randint(4500, 12500)

        perfs_du_jour = Performance.objects.filter(
            client=athlete,
            date_enregistrement__date=today
        )

        total_series_dict = perfs_du_jour.aggregate(Sum('series_realisees'))
        total_series = total_series_dict['series_realisees__sum'] or 0

        calories_brulees = total_series * 25
        calories_max = 2400

        pourcentage = 0
        if calories_max > 0:
            pourcentage = min(int((calories_brulees / calories_max) * 100), 100)

        programme_data = None
        programme_actif = Programme.objects.filter(athlete=athlete).order_by('-id').first()

        if programme_actif:
            seances_prog = Seance.objects.filter(programme=programme_actif)
            total_seances = seances_prog.count()
            seances_terminees = seances_prog.filter(est_completee=True).count()

            progression = int((seances_terminees / total_seances) * 100) if total_seances > 0 else 0

            dates = seances_prog.aggregate(debut=Min('jour_prevu'), fin=Max('jour_prevu'))

            semaine_totale = 4
            semaine_actuelle = 1

            if dates['debut'] and dates['fin']:
                jours_total = (dates['fin'] - dates['debut']).days
                semaine_totale = max(1, (jours_total // 7) + 1)

                jours_ecoules = (today - dates['debut']).days
                semaine_actuelle = max(1, min(semaine_totale, (jours_ecoules // 7) + 1))

            programme_data = {
                "titre": programme_actif.titre,
                "semaine_actuelle": semaine_actuelle,
                "semaine_totale": semaine_totale,
                "progression": progression
            }

        # --- stats_semaine ---
        debut_semaine = today - timedelta(days=today.weekday())  # Monday
        fin_semaine = debut_semaine + timedelta(days=6)

        seances_semaine_qs = Seance.objects.filter(
            q_mes_seances | q_collectives | q_indiv_vides,
            jour_prevu__gte=debut_semaine,
            jour_prevu__lte=fin_semaine
        ).distinct()

        seances_total_semaine = seances_semaine_qs.count()
        seances_faites_semaine = seances_semaine_qs.filter(est_completee=True).count()

        perfs_semaine = Performance.objects.filter(
            client=athlete,
            date_enregistrement__date__gte=debut_semaine
        )
        volume_semaine = int(sum(
            (p.poids_utilise or 0) * (p.reps_realisees or 1) * (p.series_realisees or 1)
            for p in perfs_semaine
        ))

        streak = 0
        check_date = today
        while streak < 365:
            done = Seance.objects.filter(
                q_mes_seances,
                est_completee=True,
                jour_prevu=check_date
            ).exists()
            if done:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break

        return Response({
            "prenom": athlete.user.first_name,
            "contrat": ClientSerializer(athlete).data.get("contrat"),
            "prochaine_seance": seance_data,
            "programme_actuel": programme_data,
            "stats_semaine": {
                "seances_faites": seances_faites_semaine,
                "seances_total": seances_total_semaine,
                "volume_total": volume_semaine,
                "streak": streak,
            },
            "stats_sante": {
                "pas": pas_jour,
                "calories": calories_brulees,
                "calories_max": calories_max,
                "completion_jour": pourcentage,
                "recuperation": random.randint(60, 100),
                "hydratation": round(random.uniform(1.2, 2.5), 1)
            }
        })


class AthleteStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            if not hasattr(request.user, 'client_profile'):
                return Response({"error": "Profil introuvable"}, status=400)

            athlete_profile = request.user.client_profile
            perf_qs = Performance.objects.filter(client=athlete_profile).select_related(
                'seance_exercice__seance',
                'seance_exercice__exercice'
            )

            # Count total sessions the same way as the dashboard (est_completee=True)
            coach_associe = athlete_profile.coach
            q_mes_seances = Q(programme__athlete=athlete_profile) | Q(inscriptions__client=athlete_profile)
            q_collectives = Q(est_collective=True, coach=coach_associe) if coach_associe else Q(pk__in=[])
            q_indiv_vides = Q(est_collective=False, inscriptions__isnull=True, programme__isnull=True, coach=coach_associe) if coach_associe else Q(pk__in=[])
            total_sessions = Seance.objects.filter(
                q_mes_seances | q_collectives | q_indiv_vides,
                est_completee=True
            ).distinct().count()

            total_volume_global = 0
            total_reps = 0
            muscle_totals = {}
            session_totals = {}
            personal_best = {}
            for perf in perf_qs:
                poids_num = float(perf.poids_utilise or 0)
                reps = perf.reps_realisees or 0
                series = perf.series_realisees or 1
                volume = poids_num * reps * series
                total_reps += reps * series
                total_volume_global += volume

                exercice = perf.seance_exercice.exercice
                muscle = exercice.muscle_principal or exercice.categorie or "Général"
                muscle_totals[muscle] = muscle_totals.get(muscle, 0) + int(volume)

                seance = perf.seance_exercice.seance
                session = session_totals.setdefault(seance.id, {
                    "titre": seance.titre or "Séance",
                    "date": seance.jour_prevu.strftime('%d/%m/%Y') if seance.jour_prevu else perf.date_enregistrement.strftime('%d/%m/%Y'),
                    "nb_exercices": set(),
                    "volume_total": 0,
                    "last_date": perf.date_enregistrement,
                })
                session["nb_exercices"].add(perf.seance_exercice_id)
                session["volume_total"] += int(volume)
                session["last_date"] = max(session["last_date"], perf.date_enregistrement)

                current_pr = personal_best.get(exercice.id)
                if poids_num > 0 and (not current_pr or poids_num > current_pr["best_weight"]):
                    personal_best[exercice.id] = {
                        "exercice": exercice.nom,
                        "categorie": muscle,
                        "best_weight": round(poids_num, 1),
                        "best_reps": reps,
                    }

            muscle_data = [
                {"name": name, "value": value}
                for name, value in sorted(muscle_totals.items(), key=lambda item: item[1], reverse=True)
            ]
            personal_records = sorted(personal_best.values(), key=lambda r: r["best_weight"], reverse=True)[:8]
            recent_sessions = [
                {**s, "nb_exercices": len(s["nb_exercices"])}
                for s in sorted(session_totals.values(), key=lambda x: x["last_date"], reverse=True)[:5]
            ]
            for session in recent_sessions:
                session.pop("last_date", None)

            return Response({
                "muscle_distribution": list(muscle_data),
                "personal_records": personal_records,
                "recent_sessions": recent_sessions,
                "volume_history": list(reversed(recent_sessions)),
                "summary": {
                    "total_sessions": total_sessions,
                    "total_reps": total_reps,
                    "total_volume": int(total_volume_global)
                }
            })

        except Exception as e:
            return Response({"erreur": str(e)}, status=500)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Notification.objects.filter(coach=self.request.user.coach_profile).order_by('-date_creation')
        return Notification.objects.none()

    @action(detail=True, methods=['PATCH'])
    def marquer_lu(self, request, pk=None):
        notif = self.get_object()
        notif.est_lu = True
        notif.save(update_fields=['est_lu'])
        return Response({'status': 'ok'})

    @action(detail=False, methods=['POST'])
    def marquer_tout_lu(self, request):
        notifications = self.get_queryset().filter(est_lu=False)
        count = notifications.count()
        notifications.update(est_lu=True)
        return Response({
            'status': 'Toutes les notifications ont été marquées comme lues',
            'count': count
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def athlete_reserver_seance(request, seance_id):
    if not hasattr(request.user, 'client_profile'):
        return Response(
            {"erreur": "Seul un profil athlète peut réserver une séance."},
            status=status.HTTP_403_FORBIDDEN
        )

    athlete = request.user.client_profile
    seance = get_object_or_404(Seance, id=seance_id)

    if Inscription.objects.filter(seance=seance, client=athlete).exists():
        return Response(
            {"erreur": "Vous êtes déjà inscrit ou en file d'attente pour cette séance."},
            status=status.HTTP_400_BAD_REQUEST
        )

    inscrits_confirmes = Inscription.objects.filter(seance=seance, statut='CONFIRME').count()
    capacite = seance.capacite_max if seance.capacite_max else 1

    if not athlete.peut_reserver_seance:
        return Response({"erreur": "Quota de séances atteint."}, status=status.HTTP_400_BAD_REQUEST)

    if inscrits_confirmes < capacite:
        statut_final = 'CONFIRME'
        message_succes = "Inscription confirmée avec succès !"
    else:
        statut_final = 'ATTENTE'
        message_succes = "La séance est pleine. Vous êtes sur liste d'attente."

    inscription = Inscription.objects.create(
        seance=seance,
        client=athlete,
        statut=statut_final
    )
    if statut_final == 'CONFIRME':
        _consume_seance_credit(athlete)

    jour_str = seance.jour_prevu.strftime('%d/%m/%Y') if seance.jour_prevu else 'date à définir'

    if statut_final == 'CONFIRME':
        Notification.objects.create(
            coach=seance.coach,
            seance=seance,
            type='INSCRIPTION',
            message=f"Nouvel inscrit : {athlete.prenom} {athlete.nom} s'est inscrit à la séance '{seance.titre}' du {jour_str}."
        )
    elif statut_final == 'ATTENTE':
        Notification.objects.create(
            coach=seance.coach,
            seance=seance,
            type='INFO',
            message=f"Liste d'attente : {athlete.prenom} {athlete.nom} s'est mis en file d'attente pour la séance '{seance.titre}' du {jour_str}."
        )

    return Response({
        "message": message_succes,
        "statut": statut_final,
        "inscription_id": inscription.id
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def coach_inscrire_client(request, seance_id):
    if not hasattr(request.user, 'coach_profile'):
        return Response(
            {"erreur": "Seul un coach peut inscrire un client à une séance."},
            status=status.HTTP_403_FORBIDDEN
        )

    coach = request.user.coach_profile
    seance = get_object_or_404(Seance, id=seance_id, coach=coach)

    client_id = request.data.get('client_id')
    if not client_id:
        return Response({"erreur": "client_id est requis."}, status=status.HTTP_400_BAD_REQUEST)

    client = get_object_or_404(Client, id=client_id, coach=coach)

    if Inscription.objects.filter(seance=seance, client=client).exists():
        return Response(
            {"erreur": "Ce client est déjà inscrit ou en file d'attente pour cette séance."},
            status=status.HTTP_400_BAD_REQUEST
        )

    inscrits_confirmes = Inscription.objects.filter(seance=seance, statut='CONFIRME').count()
    capacite = seance.capacite_max if seance.capacite_max else 1
    if not client.peut_reserver_seance:
        return Response({"erreur": "Quota de séances atteint pour cet athlète."}, status=status.HTTP_400_BAD_REQUEST)

    statut_final = 'CONFIRME' if inscrits_confirmes < capacite else 'ATTENTE'

    inscription = Inscription.objects.create(
        seance=seance,
        client=client,
        statut=statut_final
    )
    if statut_final == 'CONFIRME':
        _consume_seance_credit(client)

    jour_str = seance.jour_prevu.strftime('%d/%m/%Y') if seance.jour_prevu else 'date à définir'
    heure_str = seance.heure_debut.strftime('%H:%M') if seance.heure_debut else ''
    Notification.objects.create(
        coach=coach,
        seance=seance,
        type='INSCRIPTION',
        message=f"Inscrit par le coach : {client.prenom} {client.nom} ajouté à la séance '{seance.titre}' du {jour_str}."
    )
    athlete_msg = f"Nouvelle séance : {seance.titre} le {jour_str}"
    if heure_str:
        athlete_msg += f" à {heure_str}"
    NotificationAthlete.objects.create(
        client=client,
        message=athlete_msg,
        type='SEANCE'
    )

    return Response({
        "message": f"{client.prenom} {client.nom} inscrit avec succès.",
        "statut": statut_final,
        "inscription_id": inscription.id
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def athlete_annuler_reservation(request, inscription_id):
    if not hasattr(request.user, 'client_profile'):
        return Response({"erreur": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

    athlete = request.user.client_profile
    inscription = get_object_or_404(Inscription, id=inscription_id, client=athlete)

    seance = inscription.seance
    statut_avant_annulation = inscription.statut

    inscription.delete()

    if statut_avant_annulation == 'CONFIRME':
        _restore_seance_credit(athlete)
        premier_en_attente = Inscription.objects.select_for_update().filter(
            seance=seance,
            statut='ATTENTE'
        ).order_by('id').first()

        if premier_en_attente:
            _consume_seance_credit(premier_en_attente.client)
            premier_en_attente.statut = 'CONFIRME'
            premier_en_attente.save()

    return Response(
        {"message": "Votre réservation a été annulée."},
        status=status.HTTP_204_NO_CONTENT
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_athlete_calendar(request, athlete_id):
    if not hasattr(request.user, 'client_profile') or request.user.client_profile.id != athlete_id:
        return Response({"error": "Accès refusé."}, status=403)

    inscriptions = Inscription.objects.filter(
        client__id=athlete_id,
        statut='CONFIRME'
    ).select_related('seance')

    ical_content = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Athlo//Calendrier Athlete//FR",
        "CALSCALE:GREGORIAN",
    ]

    for ins in inscriptions:
        seance = ins.seance

        if seance.jour_prevu and seance.heure_debut:
            dt_start = datetime.datetime.combine(seance.jour_prevu, seance.heure_debut)
            dt_start_str = dt_start.strftime('%Y%m%dT%H%M%S')

            if seance.heure_fin:
                dt_end = datetime.datetime.combine(seance.jour_prevu, seance.heure_fin)
            else:
                dt_end = dt_start + datetime.timedelta(hours=1)

            dt_end_str = dt_end.strftime('%Y%m%dT%H%M%S')

            ical_content.extend([
                "BEGIN:VEVENT",
                f"UID:seance-{seance.id}-athlete-{athlete_id}@ton-app.com",
                f"DTSTAMP:{datetime.datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART;TZID=Europe/Paris:{dt_start_str}",
                f"DTEND;TZID=Europe/Paris:{dt_end_str}",
                f"SUMMARY:{seance.titre}",
                f"DESCRIPTION:Séance réservée via l'application.",
                "END:VEVENT"
            ])

    ical_content.append("END:VCALENDAR")

    fichier_texte = "\r\n".join(ical_content)
    response = HttpResponse(fichier_texte, content_type="text/calendar")
    response['Content-Disposition'] = f'attachment; filename="mes_entrainements_{athlete_id}.ics"'

    return response


class AthleteNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationAthleteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client_profile'):
            return NotificationAthlete.objects.filter(client=user.client_profile).order_by('-date_creation')
        return NotificationAthlete.objects.none()

    @action(detail=True, methods=['PATCH'])
    def marquer_lu(self, request, pk=None):
        notif = self.get_object()
        notif.est_lu = True
        notif.save(update_fields=['est_lu'])
        return Response({'status': 'ok'})

    @action(detail=False, methods=['POST'])
    def marquer_tout_lu(self, request):
        self.get_queryset().update(est_lu=True)
        return Response({'status': 'ok'})


class DemoStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "total_exercices": Exercice.objects.count(),
            "total_coachs": Coach.objects.count()
        })


class CoachAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Accès réservé aux coachs."}, status=403)

        coach = request.user.coach_profile
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6)

        total_athletes = Client.objects.filter(coach=coach).count()
        contrats_actifs = ContratAthlete.objects.filter(coach=coach, statut='ACTIF').filter(
            Q(type_contrat='ABONNEMENT', date_debut__lte=today, date_expiration__gte=today) |
            Q(type_contrat__in=['PACK', 'UNITE'], seances_restantes__gt=0)
        ).values('client_id').distinct().count()

        # --- LOGIQUE SÉANCES (Existante) ---
        seances_globales = Seance.objects.filter(
            Q(coach=coach) | Q(programme__coach=coach)
        ).distinct()

        seances_7_jours = seances_globales.filter(
            jour_prevu__range=[seven_days_ago, today]
        )

        total_seances = seances_7_jours.count()
        seances_completees = seances_7_jours.filter(est_completee=True).count()

        completion_rate = 0
        if total_seances > 0:
            completion_rate = int((seances_completees / total_seances) * 100)

        # --- NOUVELLE LOGIQUE REVENUS (Reporting Réel) ---
        # On calcule le Chiffre d'Affaires total généré par ce coach
        total_ca = Commande.objects.filter(
            coach=coach, 
            status='PAID'
        ).aggregate(Sum('montant_ttc'))['montant_ttc__sum'] or 0

        chart_data = []
        for i in range(7):
            date_target = seven_days_ago + timedelta(days=i)
            count_day = seances_7_jours.filter(
                jour_prevu=date_target,
                est_completee=True
            ).count()

            chart_data.append({
                "day": date_target.strftime('%a'),
                "sessions": count_day
            })

        return Response({
            "total_athletes": total_athletes,
            "contrats_actifs": contrats_actifs,
            "completion_rate": completion_rate,
            "total_volume": round(total_ca, 2), # On remplace le volume fictif par le CA réel
            "chart_data": chart_data,
            "period": "7 derniers jours"
        })

class CoachCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, coach_id=None):
        if hasattr(request.user, 'coach_profile'):
            coach = request.user.coach_profile
            if coach_id is not None and coach.id != coach_id:
                return Response({"error": "Action non autorisée."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.is_staff:
            coach = get_object_or_404(Coach, id=coach_id)
        else:
            return Response({"error": "Action non autorisée."}, status=status.HTTP_403_FORBIDDEN)

        seances = Seance.objects.filter(coach=coach).prefetch_related('inscriptions__client')

        data = []
        for s in seances:
            inscriptions = s.inscriptions.all()

            if s.est_collective:
                noms = [f"{ins.client.prenom} {ins.client.nom.upper()}" for ins in inscriptions]
                client_display = ", ".join(noms) if noms else "Aucun inscrit"
            else:
                athlete_explicite = inscriptions.first().client if inscriptions.exists() else None
                athlete = athlete_explicite or (s.programme.athlete if s.programme else None)
                client_display = f"{athlete.prenom} {athlete.nom.upper()}" if athlete else "En attente"

            participants_data = [
                {
                    "id": ins.id,
                    "client_id": ins.client.id,
                    "client_name": f"{ins.client.prenom} {ins.client.nom}",
                    "statut": ins.statut,
                    "date_inscription": ins.date_inscription.isoformat() if ins.date_inscription else None,
                } for ins in inscriptions
            ]

            if not s.est_collective and s.programme and s.programme.athlete:
                if not any(p['client_id'] == s.programme.athlete.id for p in participants_data):
                    participants_data.append({
                        "id": f"prog-{s.programme.athlete.id}",
                        "client_id": s.programme.athlete.id,
                        "client_name": f"{s.programme.athlete.prenom} {s.programme.athlete.nom}",
                        "statut": "CONFIRME",
                        "date_inscription": str(s.jour_prevu) if s.jour_prevu else None
                    })

            vrai_nb_inscrits = len([p for p in participants_data if p['statut'] == 'CONFIRME'])

            start_dt = f"{s.jour_prevu}T{s.heure_debut}" if s.heure_debut else str(s.jour_prevu)
            end_dt = f"{s.jour_prevu}T{s.heure_fin}" if s.heure_fin else start_dt

            data.append({
                "id": s.id,
                "db_id": s.id,
                "title": s.titre,
                "start": start_dt,
                "end": end_dt,
                "client_name": client_display,
                "is_collective": s.est_collective,
                "est_collective": s.est_collective,
                "completed": s.est_completee,
                "est_completee": s.est_completee,
                "capacite_max": s.capacite_max,
                "salle": s.salle_id,
                "salle_id": s.salle_id,
                "salle_nom": s.salle.nom if s.salle else "",
                "nombre_inscrits": vrai_nb_inscrits,
                "type": "collective" if s.est_collective else "individuelle",
                "participants": participants_data
            })

        return Response(data)


class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Indisponibilite.objects.filter(coach=self.request.user.coach_profile)
        return Indisponibilite.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            raise PermissionDenied("Seuls les coachs peuvent créer des indisponibilités.")

    def perform_update(self, serializer):
        instance_avant = self.get_object()
        ancien_jour = instance_avant.jour_prevu
        ancienne_heure_debut = instance_avant.heure_debut
        ancienne_heure_fin = instance_avant.heure_fin

        nouvelle_indispo = serializer.save()

        horaire_modifie = (
            ancien_jour != nouvelle_indispo.jour_prevu or
            ancienne_heure_debut != nouvelle_indispo.heure_debut or
            ancienne_heure_fin != nouvelle_indispo.heure_fin
        )

        if horaire_modifie:
            type_event = "congé" if nouvelle_indispo.est_conge else "indisponibilité"

            Notification.objects.create(
                coach=nouvelle_indispo.coach,
                seance=None,
                type='MODIFICATION',
                message=f"L'horaire de votre {type_event} '{nouvelle_indispo.titre}' a été modifié pour le {nouvelle_indispo.jour_prevu}."
            )


class PerformanceCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        athlete = getattr(request.user, 'client_profile', None)
        if not athlete:
            return Response({"erreur": "Profil athlète introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        seance_id = request.data.get('seance_id')
        exercices_data = request.data.get('exercices', [])
        if not exercices_data and request.data.get('seance_exercice'):
            exercices_data = [request.data]
            seance_exercice = get_object_or_404(SeanceExercice, id=request.data.get('seance_exercice'))
            seance_id = seance_exercice.seance_id

        if not seance_id:
              return Response({"erreur": "seance_id est requis."}, status=status.HTTP_400_BAD_REQUEST)

        seance = get_object_or_404(Seance, id=seance_id)
        if not seance.inscriptions.filter(client=athlete).exists():
            return Response({"erreur": "Vous n'êtes pas inscrit à cette séance."}, status=status.HTTP_403_FORBIDDEN)
        created = []
        skipped = []

        for idx, item in enumerate(exercices_data):
            # Accept multiple possible frontend key names for robustness
            seance_exercice_id = item.get('seance_exercice')
            exercice_id = item.get('exercice_id') or item.get('exerciceId') or item.get('id')
            series_realisees = item.get('series_realisees') if item.get('series_realisees') is not None else item.get('series')
            reps_realisees = item.get('reps_realisees') if item.get('reps_realisees') is not None else item.get('reps')
            poids_utilise_val = item.get('poids_moyen') if item.get('poids_moyen') is not None else item.get('poids')
            if not (seance_exercice_id or exercice_id):
                skipped.append({'index': idx, 'reason': 'missing_exercice_id', 'item': item})
                continue
            if seance_exercice_id:
                seance_exercice = SeanceExercice.objects.filter(seance=seance, id=seance_exercice_id).first()
            else:
                seance_exercice = SeanceExercice.objects.filter(seance=seance, exercice_id=exercice_id).first()
            if not seance_exercice:
                skipped.append({'index': idx, 'exercice_id': exercice_id, 'reason': 'not_in_seance'})
                continue
            Performance.objects.create(
                client=athlete,
                seance_exercice=seance_exercice,
                series_realisees=series_realisees or 0,
                reps_realisees=reps_realisees or 0,
                poids_utilise=poids_utilise_val or 0.0,
                notes_athlete=item.get('notes') or request.data.get('notes', ''),
            )
            created.append(exercice_id)

        seance.est_completee = True
        seance.save(update_fields=['est_completee'])

        return Response({
            "message": f"{len(created)} performance(s) enregistrée(s).",
            "created": created,
            "skipped": skipped
        }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def export_coach_calendar(request, coach_id):
    coach = get_object_or_404(Coach, id=coach_id)
    cal = Calendar()

    cal.add('prodid', '-//Agenda Athlo Coach//athlo.com//')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', f'Agenda Athlo - {coach.user.first_name}')

    seances = Seance.objects.filter(coach=coach)
    for seance in seances:
        if not seance.jour_prevu or not seance.heure_debut or not seance.heure_fin:
            continue

        event = Event()
        event.add('summary', seance.titre if seance.titre else 'Séance de coaching')

        dt_start = datetime.datetime.combine(seance.jour_prevu, seance.heure_debut)
        dt_end = datetime.datetime.combine(seance.jour_prevu, seance.heure_fin)

        event.add('dtstart', dt_start)
        event.add('dtend', dt_end)
        event.add('description', 'Séance Collective' if seance.est_collective else 'Séance Individuelle')

        cal.add_component(event)

    indispos = Indisponibilite.objects.filter(coach=coach)
    for indispo in indispos:
        if not indispo.jour_prevu or not indispo.heure_debut or not indispo.heure_fin:
            continue

        event = Event()
        event.add('summary', indispo.titre if indispo.titre else 'Indisponible')

        dt_start = datetime.datetime.combine(indispo.jour_prevu, indispo.heure_debut)
        dt_end = datetime.datetime.combine(indispo.jour_prevu, indispo.heure_fin)

        event.add('dtstart', dt_start)
        event.add('dtend', dt_end)
        event.add('description', 'Congé' if indispo.est_conge else 'Indisponibilité')

        cal.add_component(event)

    response = HttpResponse(cal.to_ical(), content_type="text/calendar")
    response['Content-Disposition'] = f'attachment; filename="athlo_agenda_{coach_id}.ics"'

    return response


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_inscription_status(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    if ins.seance.coach.user != request.user:
        return Response({"error": "Action non autorisée."}, status=status.HTTP_403_FORBIDDEN)
    ancien_statut = ins.statut
    nouveau_statut = request.data.get('statut')
    if ancien_statut == 'ATTENTE' and nouveau_statut == 'CONFIRME':
        _consume_seance_credit(ins.client)
    elif ancien_statut == 'CONFIRME' and nouveau_statut in ['ATTENTE', 'ANNULE']:
        _restore_seance_credit(ins.client)
    Inscription.objects.filter(id=inscription_id).update(statut=nouveau_statut)
    ins.refresh_from_db()

    if ancien_statut == 'ATTENTE' and nouveau_statut == 'CONFIRME':
        client_name = f"{ins.client.prenom} {ins.client.nom}"
        Notification.objects.create(
            coach=ins.seance.coach,
            seance=ins.seance,
            message=f"{client_name} a été promu(e) de la liste d'attente et est maintenant confirmé(e) pour : {ins.seance.titre}",
            type='INSCRIPTION'
        )
    return Response({"status": "ok"})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_participant(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    if ins.seance.coach.user != request.user:
        return Response({"error": "Action non autorisée."}, status=status.HTTP_403_FORBIDDEN)
    coach = ins.seance.coach
    client_name = f"{ins.client.prenom} {ins.client.nom}"
    seance = ins.seance
    seance_titre = ins.seance.titre
    if ins.statut == 'CONFIRME':
        _restore_seance_credit(ins.client)
    ins.delete()

    Notification.objects.create(
        coach=coach,
        seance=seance,
        message=f"{client_name} s'est désinscrit de la séance : {seance_titre}",
        type='DESINSCRIPTION'
    )
    return Response(status=204)


class MarquerSeanceRateeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, seance_id):
        print(f"--- DÉCLENCHEMENT SÉANCE RATÉE POUR L'ID {seance_id} ---")

        if not hasattr(request.user, 'client_profile'):
            return Response({"error": "Action non autorisée"}, status=403)

        athlete = request.user.client_profile
        seance = get_object_or_404(Seance, id=seance_id)

        inscription = seance.inscriptions.filter(client=athlete).first()
        if not inscription:
            return Response({"error": "Action non autorisée"}, status=403)
        if inscription.statut != 'ABSENT':
            inscription.statut = 'ABSENT'
            inscription.save()
            print(f"  Inscription de l'athlète {athlete.id} passée en ABSENT.")

        Seance.objects.filter(id=seance_id).update(est_completee=True)
        print(f" Séance {seance_id} forcée à est_completee=True dans la BDD.")

        return Response({"message": "Séance marquée comme ratée et terminée."})


class ProspectCoachListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = Coach.objects.select_related('user').prefetch_related('avis', 'programmes_crees').all()

        ville = request.GET.get('ville')
        specialite = request.GET.get('specialite')
        prix_max = request.GET.get('prix_max')
        type_offre = request.GET.get('type_offre')
        note_min = request.GET.get('note_min')

        lat = request.GET.get("lat")
        lng = request.GET.get("lng")
        distance_max = request.GET.get("distance_max")

        if ville:
            queryset = queryset.filter(ville__icontains=ville)

        if specialite:
            queryset = queryset.filter(
                Q(specialite__icontains=specialite) |
                Q(specialites_tags__icontains=specialite)
            )

        distance_map = {}

        if lat and lng:
            try:
                lat = float(lat)
                lng = float(lng)

                temp = []

                for coach in queryset:
                    ville_coach = (coach.ville or "").strip().lower()

                    coords = None
                    for ville_ref, ville_coords in VILLE_COORDS.items():
                        if ville_ref.lower() == ville_coach:
                            coords = ville_coords
                            break

                    if coords:
                        d = calcul_distance(lat, lng, coords[0], coords[1])
                        distance_map[coach.id] = d
                        temp.append((d, coach))
                    else:
                        distance_map[coach.id] = None
                        temp.append((9999, coach))

                if distance_max:
                    try:
                        distance_max = float(distance_max)
                        temp = [(d, c) for d, c in temp if d <= distance_max]
                    except Exception:
                        pass

                temp.sort(key=lambda x: x[0])
                queryset = [c for _, c in temp]

            except Exception:
                return Response({"error": "lat/lng invalides"}, status=400)

        coaches_data = ProspectCoachListSerializer(queryset, many=True).data

        for c in coaches_data:
            c['distance'] = distance_map.get(c['id'])

        if note_min:
            try:
                note_min = float(note_min)
                coaches_data = [
                    c for c in coaches_data
                    if float(c['note_moyenne']) >= note_min
                ]
            except ValueError:
                pass

        if prix_max:
            try:
                prix_max = float(prix_max)

                if type_offre and type_offre != 'tous':
                    coaches_data = [
                        c for c in coaches_data
                        if c.get('offres_tarifs', {}).get(type_offre) is not None
                        and float(c['offres_tarifs'][type_offre]) <= prix_max
                    ]
                else:
                    coaches_data = [
                        c for c in coaches_data
                        if any(
                            float(v) <= prix_max
                            for v in c.get('offres_tarifs', {}).values()
                            if v is not None
                        )
                    ]
            except ValueError:
                pass

        return Response(coaches_data)


class ProspectCoachDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, coach_id):
        coach = get_object_or_404(
            Coach.objects.select_related('user').prefetch_related('avis', 'programmes_crees'),
            id=coach_id
        )
        serializer = ProspectCoachDetailSerializer(coach)
        return Response(serializer.data)
class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # On récupère le profil athlète de l'utilisateur connecté
            client = request.user.client_profile
            data = request.data
            montant_ttc = data.get('montant_ttc', data.get('total', 0))

            # 1. Création de la commande principale
            commande = Commande.objects.create(
                client=client,
                adresse_livraison=data.get('adresse_livraison', ''),
                montant_ttc=montant_ttc,
                montant_ht=round(float(montant_ttc or 0) / 1.2, 2),
                status='PENDING',

            )

            # 2. Création des lignes de commande
            lignes_data = data.get('lignes', [])
            for ligne in lignes_data:
                produit = Produit.objects.get(id=ligne['produit_id'])
                LigneCommande.objects.create(
                    commande=commande,
                    produit=produit,
                    quantite=ligne['quantite'],
                    prix_unitaire=ligne['prix_unitaire']
                )

            return Response(
                {"message": "Commande créée avec succès", "id": commande.id}, 
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
class AthleteCommandeHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"error": "Accès réservé aux athlètes."}, status=403)
        
        # On récupère toutes les commandes de l'athlète connecté
        commandes = Commande.objects.filter(client=request.user.client_profile).order_by('-date_commande')
        serializer = CommandeSerializer(commandes, many=True)
        return Response(serializer.data)
