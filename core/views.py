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
        client, _ = Client.objects.get_or_create(user=request.user)
        serializer = ClientSerializer(client, data=request.data, partial=True)
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
        if hasattr(user, 'coach_profile'): return Programme.objects.filter(coach=user.coach_profile)
        return Programme.objects.filter(athlete=user.client_profile)

class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)).distinct()
        return Seance.objects.filter(programme__athlete=user.client_profile)

# --- 4. DASHBOARD & STATS (AVEC TON MOCK ET TA LOGIQUE) ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        client = request.user.client_profile
        prochaine_seance = Seance.objects.filter(
            Q(programme__athlete=client) | Q(inscriptions__client=client),
            est_completee=False
        ).order_by('jour_prevu', 'heure_debut', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            nb_exos = prochaine_seance.exercices_details.count()
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "duree_estimee": nb_exos * 10 or 45,
                "calories_estimees": nb_exos * 80 or 450,
            }

        today = timezone.now().date()
        random.seed(client.id + today.toordinal()) # TON MOCK INTELLIGENT
        pas_jour = random.randint(4500, 12500)
        
        return Response({
            "prenom": client.prenom,
            "prochaine_seance": seance_data,
            "stats_sante": {
                "pas": pas_jour,
                "calories": 0,
                "recuperation": random.randint(60, 100)
            }
        })

class AthleteStatsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        client = request.user.client_profile
        volume_data = Performance.objects.filter(client=client).annotate(day=TruncDate('date_enregistrement')).values('day').annotate(
            total_volume=Sum(ExpressionWrapper(F('poids_utilise') * F('reps_realisees') * F('series_realisees'), output_field=FloatField()))
        ).order_by('day')[:7]
        
        muscle_data = Performance.objects.filter(client=client).values(name=F('seance_exercice__exercice__categorie')).annotate(value=Sum('reps_realisees')).order_by('-value')
        formatted_volume = [{"day": entry['day'].strftime('%a') if entry['day'] else "N/A", "volume": entry['total_volume'] or 0} for entry in volume_data]
        
        return Response({
            "volume_history": formatted_volume,
            "muscle_distribution": list(muscle_data),
            "summary": {
                "total_sessions": Performance.objects.filter(client=client).values('seance_exercice__seance').distinct().count(),
                "total_reps": Performance.objects.filter(client=client).aggregate(Sum('reps_realisees'))['reps_realisees__sum'] or 0
            }
        })

# --- 5. NOTIFICATIONS ---

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self): return Notification.objects.filter(coach=self.request.user.coach_profile)

class AthleteNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationAthleteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # On vérifie si l'utilisateur a bien un profil client (athlète)
        if hasattr(user, 'client_profile'):
            return NotificationAthlete.objects.filter(client=user.client_profile)
        
        # Si c'est un admin ou un coach sans profil athlète, on renvoie rien (0 erreur)
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
    def perform_create(self, serializer): serializer.save(client=self.request.user.client_profile)

class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    def get_queryset(self): return Indisponibilite.objects.filter(coach=self.request.user.coach_profile)

@api_view(['PATCH'])
def update_inscription_status(request, inscription_id): return Response({"status": "ok"})

@api_view(['DELETE'])
def remove_participant(request, inscription_id): return Response(status=204)

@api_view(['GET'])
def export_coach_calendar(request, coach_id): return HttpResponse("iCal", content_type="text/calendar")