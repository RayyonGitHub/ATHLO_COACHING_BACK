import random 
import datetime
import string
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q, Sum, F, ExpressionWrapper, FloatField
from django.db.models.functions import TruncDate
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from icalendar import Calendar, Event
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.core.mail import send_mail
from collections import defaultdict
import re
from django.db.models import Sum, F
from django.utils.timezone import localtime
from rest_framework import viewsets, status, generics
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

# --- IMPORTS MODÈLES & SERIALIZERS ---
from .models import (
    Client, Coach, Exercice, Programme, Seance, 
    SeanceExercice, Performance, Indisponibilite, 
    Inscription, Notification, NotificationAthlete, Salle, Avis
)
from .serializers import (
    ClientSerializer, CoachSerializer, ExerciceSerializer, 
    ProgrammeSerializer, SeanceSerializer, PerformanceSerializer, 
    IndisponibiliteSerializer, NotificationSerializer, 
    NotificationAthleteSerializer, SalleSerializer, AvisSerializer
)
# --- 1. SÉCURITÉ & AUTH ---

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
        user = authenticate(username=request.data.get("email"), password=request.data.get("password"))
        if not user: return Response({"error": "Invalid credentials"}, status=401)
        refresh = RefreshToken.for_user(user)
        role = 'coach' if hasattr(user, 'coach_profile') else 'athlete' if hasattr(user, 'client_profile') else 'prospect'
        return Response({
            "token": str(refresh.access_token),
            "user": {"id": user.id, "email": user.email, "role": role}
        })

# --- 2. GESTION DES PROFILS ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def generate_password(self, length=10):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def perform_create(self, serializer):
        coach_profile = self.request.user.coach_profile
        email = serializer.validated_data.get('email')
        temp_password = self.generate_password()
        user = User.objects.create_user(
            username=email, email=email, password=temp_password,
            first_name=serializer.validated_data.get('prenom'),
            last_name=serializer.validated_data.get('nom')
        )
        serializer.save(coach=coach_profile, user=user)

class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        coach, _ = Coach.objects.get_or_create(user=request.user)
        return Response(CoachSerializer(coach).data)
    def patch(self, request):
        coach, _ = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

class AthleteMeView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request):
        # Correction : Ton modèle de base est 'Client'
        athlete_profile, _ = Client.objects.get_or_create(user=request.user)
        serializer = ClientSerializer(athlete_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# --- 3. VUES SPORTIVES ---

class ExerciceViewSet(viewsets.ModelViewSet):
    queryset = Exercice.objects.all()
    serializer_class = ExerciceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ['categorie']

class ProgrammeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgrammeSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'): 
            return Programme.objects.filter(coach=user.coach_profile)
        if hasattr(user, 'client_profile'):
            return Programme.objects.filter(athlete=user.client_profile)
        return Programme.objects.none()

    def perform_create(self, serializer):
        # 1. Récupération du coach (indispensable)
        coach = getattr(self.request.user, 'coach_profile', None)
        if not coach:
            raise ValidationError({"error": "Profil coach introuvable. Action refusée."})

        # 2. Sauvegarde du programme
        # On force le coach ici pour respecter la contrainte NOT NULL
        programme = serializer.save(coach=coach)
        
        # 3. Tentative de notification (Isolée pour éviter la 500)
        try:
            # On récupère l'athlète lié au programme
            athlete_obj = getattr(programme, 'athlete', None)
            
            if athlete_obj:
                NotificationAthlete.objects.create(
                    client=athlete_obj, # 🎯 CHANGEMENT ICI : 'client=' au lieu de 'athlete='
                    message=f"Nouveau programme : {programme.titre}",
                    type='SEANCE' 
                )
                print(f"✅ Notification envoyée à l'ID {athlete_obj.id}")
        except Exception as e:
            # Si ça plante ici, on affiche l'erreur dans le terminal
            # MAIS l'utilisateur reçoit une réponse 201 (Succès) pour le programme
            print(f"⚠️ Erreur notification (mais programme créé) : {e}")
class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(
                Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)
            ).distinct()
        if hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    def create(self, request, *args, **kwargs):
        print("\n=== 🕵️‍♂️ DEBUG CRÉATION SÉANCE ===")
        print(f"1. Données reçues du Front : {request.data}")
        
        try:
            # Séparation des exercices et de la séance
            # request.data peut être un QueryDict, on s'assure de pouvoir le modifier
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            exercices_data = data.pop('exercices', [])
            
            print(f"2. Données nettoyées pour la séance : {data}")
            
            serializer = self.get_serializer(data=data)
            
            # Si le Serializer bloque, on verra pourquoi ici !
            if not serializer.is_valid():
                print(f"❌ LE SERIALIZER BLOQUE : {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            print("3. Serializer valide. Sauvegarde en cours...")
            self.perform_create(serializer)
            seance_creee = serializer.instance
            print(f"✅ Séance créée (ID: {seance_creee.id})")

            # Création des exercices
            if exercices_data:
                print(f"4. Tentative d'ajout de {len(exercices_data)} exercices...")
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
                print("✅ Tous les exercices ont été ajoutés !")

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
        except Exception as e:
            import traceback
            print("💥 CRASH FATAL :")
            print(traceback.format_exc()) # Affiche TOUT le chemin de l'erreur
            return Response({"erreur_interne": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_create(self, serializer):
        coach = getattr(self.request.user, 'coach_profile', None)
        serializer.save(coach=coach)
    @action(detail=True, methods=['get'], url_path='resume')
    def get_resume(self, request, pk=None):
        """Récupère le détail de ce que l'athlète a réellement fait pendant cette séance"""
        seance = self.get_object()
        athlete = getattr(request.user, 'client_profile', None)
        
        if not athlete:
            return Response({"error": "Seul un athlète peut voir son résumé"}, status=400)

        # On va chercher les perfs liées à cette séance pour cet athlète
        # Note : On utilise 'seance_exercice__seance' car Performance pointe vers SeanceExercice
        perfs = Performance.objects.filter(
            client=athlete,
            seance_exercice__seance=seance
        ).select_related('seance_exercice__exercice')

        resultats = []
        total_volume = 0

        for p in perfs:
            # Extraction du poids (on garde ta logique robuste)
            poids_str = str(p.poids_utilise).replace(',', '.')
            nombres = re.findall(r"[-+]?\d*\.\d+|\d+", poids_str)
            poids_num = float(nombres[0]) if nombres else 0.0
            
            vol_exo = poids_num * (p.reps_realisees or 0) * (p.series_realisees or 1)
            total_volume += vol_exo

            resultats.append({
                "exercice": p.seance_exercice.exercice.nom,
                "series": p.series_realisees,
                "reps": p.reps_realisees,
                "poids": p.poids_utilise,
                "volume_exercice": int(vol_exo)
            })

        return Response({
            "titre_seance": seance.titre,
            # 🎯 ON UTILISE 'jour_prevu' ICI :
            "date": seance.jour_prevu.strftime("%d/%m/%Y") if seance.jour_prevu else "Date libre",
            "exercices": resultats,
            "volume_total": int(total_volume),
            "ressenti": seance.ressenti_client, # Petit bonus : on renvoie le ressenti
            "notes": seance.notes_client        # et les notes si besoin
        })   
# --- 4. DASHBOARD & STATS (AVEC TON MOCK ET TA LOGIQUE) ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        athlete = request.user.client_profile
        today = timezone.now().date()
        
        # --- 1. GESTION DE LA PROCHAINE SÉANCE ---
        prochaine_seance = Seance.objects.filter(
            Q(programme__athlete=athlete) | Q(inscriptions__client=athlete),
            est_completee=False
        ).order_by('jour_prevu', 'heure_debut', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            # Sécurité pour éviter un crash si hasattr
            nb_exos = prochaine_seance.exercices_details.count() if hasattr(prochaine_seance, 'exercices_details') else 0
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "duree_estimee": nb_exos * 10 or 45,
                "calories_estimees": nb_exos * 80 or 450,
            }

        # --- 2. GESTION DES STATS SANTÉ & CALORIES ---
        random.seed(athlete.id + today.toordinal()) 
        pas_jour = random.randint(4500, 12500)
        
        # On va chercher les exercices terminés AUJOURD'HUI par CET athlète
        perfs_du_jour = Performance.objects.filter(
            client=athlete, 
            date_enregistrement__date=today
        )
        
        # On additionne toutes les "séries réalisées" de la journée
        total_series_dict = perfs_du_jour.aggregate(Sum('series_realisees'))
        total_series = total_series_dict['series_realisees__sum'] or 0
        
        # FORMULE MAGIQUE : Disons qu'une série d'exercices brûle en moyenne 25 calories
        calories_brulees = total_series * 25
        
        calories_max = 2400
        
        # Calcul du pourcentage (le min() sert à bloquer le cercle à 100% max)
        pourcentage = 0
        if calories_max > 0:
            pourcentage = min(int((calories_brulees / calories_max) * 100), 100)
        
        return Response({
            "prenom": athlete.user.first_name, # Ou athlete.prenom selon ton modèle
            "prochaine_seance": seance_data,
            "stats_sante": {
                "pas": pas_jour,
                "calories": calories_brulees,
                "calories_max": calories_max,
                "completion_jour": pourcentage, # <-- LA CLÉ POUR LE CADRAN ORANGE !
                "recuperation": random.randint(60, 100),
                "hydratation": round(random.uniform(1.2, 2.5), 1) # Petit bonus aléatoire
            }
        })
class AthleteStatsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        print("\n=== 📊 DEBUG STATS ATHLÈTE ===")
        try:
            # 1. Vérification du profil
            if not hasattr(request.user, 'client_profile'):
                print("❌ L'utilisateur n'a pas de client_profile")
                return Response({"error": "Profil introuvable"}, status=400)
                
            athlete_profile = request.user.client_profile
            perf_qs = Performance.objects.filter(client=athlete_profile)
            
            # 2. Stats simples
            total_sessions = perf_qs.values('seance_exercice__seance').distinct().count()
            total_reps_dict = perf_qs.aggregate(Sum('reps_realisees'))
            total_reps = total_reps_dict['reps_realisees__sum'] or 0
            
            # 3. CALCUL DU VOLUME SÉCURISÉ (En Python)
            volume_par_jour = defaultdict(float)
            total_volume_global = 0
            
            for perf in perf_qs:
                # On extrait juste le nombre (ex: "20kg" -> 20.0, "Poids du corps" -> 0.0)
                poids_str = str(perf.poids_utilise).replace(',', '.')
                nombres = re.findall(r"[-+]?\d*\.\d+|\d+", poids_str)
                poids_num = float(nombres[0]) if nombres else 0.0
                
                reps = perf.reps_realisees or 0
                series = perf.series_realisees or 1
                volume = poids_num * reps * series
                
                total_volume_global += volume
                
                # Pour le graphique de l'historique
                if perf.date_enregistrement:
                    jour = perf.date_enregistrement.strftime('%a')
                    volume_par_jour[jour] += volume

            # Formatage pour le graphique de volume
            formatted_volume = [
                {"day": jour, "volume": int(vol)} 
                for jour, vol in volume_par_jour.items()
            ]
            
            # 4. Répartition Musculaire
            muscle_data = perf_qs.values(
                name=F('seance_exercice__exercice__categorie')
            ).annotate(value=Sum('reps_realisees')).order_by('-value')
            
            print(f"✅ Stats réussies : {total_sessions} sessions, {int(total_volume_global)} kg de volume")

            return Response({
                "volume_history": formatted_volume,
                "muscle_distribution": list(muscle_data),
                "summary": {
                    "total_sessions": total_sessions,
                    "total_reps": total_reps,
                    "total_volume": int(total_volume_global) # 🎯 LA DONNÉE POUR LA CASE VIOLETTE !
                }
            })
            
        except Exception as e:
            import traceback
            print("💥 CRASH DANS LES STATS :")
            print(traceback.format_exc())
            return Response({"erreur": str(e)}, status=500)
# --- 5. NOTIFICATIONS ---
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self): 
        # On s'assure que le coach ne voit que ses propres alertes
        if hasattr(self.request.user, 'coach_profile'):
            return Notification.objects.filter(coach=self.request.user.coach_profile)
        return Notification.objects.none()

class AthleteNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationAthleteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client_profile'):
            # BINGO : on remet 'client=' car c'est le vrai nom en base de données !
            return NotificationAthlete.objects.filter(client=user.client_profile)
        return NotificationAthlete.objects.none()

    @action(detail=False, methods=['POST'])
    def marquer_tout_lu(self, request):
        self.get_queryset().update(est_lu=True)
        return Response({'status': 'ok'})
# --- 6. AUTRES (DÉMO, CALENDRIER, ETC.) ---

class DemoStatsView(APIView): # <-- CELLE QUI MANQUAIT
    permission_classes = [AllowAny]
    def get(self, request):
        return Response({"total_exercices": Exercice.objects.count(), "total_coachs": Coach.objects.count()})

class CoachAnalyticsView(APIView):
    def get(self, request): return Response({"total_athletes": 0})

class CoachCalendarView(APIView):
    def get(self, request, coach_id=None): return Response([])

class PerformanceCreateView(generics.CreateAPIView):
    serializer_class = PerformanceSerializer
    def perform_create(self, serializer):
        serializer.save(client=self.request.user.client_profile)
class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    def get_queryset(self): return Indisponibilite.objects.filter(coach=self.request.user.coach_profile)

@api_view(['PATCH'])
def update_inscription_status(request, inscription_id): return Response({"status": "ok"})

@api_view(['DELETE'])
def remove_participant(request, inscription_id): return Response(status=204)

@api_view(['GET'])
def export_coach_calendar(request, coach_id): return HttpResponse("iCal", content_type="text/calendar")