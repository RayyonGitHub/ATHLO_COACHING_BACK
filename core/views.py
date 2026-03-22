import datetime
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q, Sum, F, ExpressionWrapper, FloatField
from django.db.models.functions import TruncDate
from django.contrib.auth import authenticate
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
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from icalendar import Calendar, Event

from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite, Inscription, Notification
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer, IndisponibiliteSerializer, NotificationSerializer

# --- Vues Profils ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def generate_password(self, length=10):
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def perform_create(self, serializer):
        coach_profile = self.request.user.coach_profile
        email = serializer.validated_data.get('email')

        existing_user = User.objects.filter(email=email).first()
        existing_client = Client.objects.filter(email=email).first()

        if existing_user and existing_client:
            client = existing_client
            client.coach = coach_profile
            client.nom = serializer.validated_data.get('nom')
            client.prenom = serializer.validated_data.get('prenom')
            client.save()
            return 
        elif existing_user:
            raise ValidationError("Un utilisateur avec cet email existe déjà.")

        temp_password = self.generate_password()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=temp_password,
            first_name=serializer.validated_data.get('prenom'),
            last_name=serializer.validated_data.get('nom')
        )

        serializer.save(coach=coach_profile, user=user)

        send_mail(
            subject="Vos identifiants de connexion",
            message=f"Bonjour {serializer.validated_data.get('prenom')},\n\nVotre compte coach a été créé.\nEmail: {email}\nMot de passe: {temp_password}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user:
            instance.user.delete()
        instance.delete()
        return Response(status=204)

class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        return Response(CoachSerializer(coach).data)

    def patch(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AthleteMeView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request):
        client, created = Client.objects.get_or_create(
            user=request.user,
            defaults={'email': request.user.email, 'nom': request.user.last_name, 'prenom': request.user.first_name}
        )
        serializer = ClientSerializer(client, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# --- VUES SPORTIVES ---

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
        elif hasattr(user, 'client_profile'):
            return Programme.objects.filter(athlete=user.client_profile)
        return Programme.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            raise PermissionDenied("Seuls les coachs peuvent créer un programme.")

class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)).distinct()
        elif hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    @transaction.atomic 
    def create(self, request, *args, **kwargs):
        data = request.data
        programme_id = data.get('programme_id')

        if not programme_id:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save(coach=request.user.coach_profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        programme = get_object_or_404(Programme, id=programme_id)
        seance = Seance.objects.create(
            coach=request.user.coach_profile,
            programme=programme,
            titre=data.get('titre'),
            ordre=Seance.objects.filter(programme=programme).count() + 1
        )

        for exo_data in data.get('exercices', []):
            exercice = get_object_or_404(Exercice, id=exo_data.get('exercice_id'))
            # On retire l'id pour ne pas l'envoyer en double dans le create
            params = exo_data.copy()
            params.pop('exercice_id', None)
            SeanceExercice.objects.create(seance=seance, exercice=exercice, **params)

        return Response(self.get_serializer(seance).data, status=status.HTTP_201_CREATED)

# --- ANALYTICS ET DASHBOARD ATHLÈTE ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
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
                "programme_titre": prochaine_seance.programme.titre if prochaine_seance.programme else "Séance indépendante",
                "duree_estimee": nb_exos * 10 or 45,
                "calories_estimees": nb_exos * 80 or 450,
            }

        programme_actuel = Programme.objects.filter(athlete=client).last()
        prog_data = None
        if programme_actuel:
            total = Seance.objects.filter(programme=programme_actuel).count()
            faits = Seance.objects.filter(programme=programme_actuel, est_completee=True).count()
            prog_data = {
                "titre": programme_actuel.titre, 
                "progression": int((faits/total)*100) if total > 0 else 0
            }

        return Response({
            "prenom": client.prenom,
            "prochaine_seance": seance_data,
            "programme_actuel": prog_data,
            "stats_sante": {"completion_jour": 0, "calories": 0, "calories_max": 2500}
        })

class AthleteStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"detail": "Accès réservé aux athlètes."}, status=403)
        
        client = request.user.client_profile
        
        # 1. Calcul du Volume d'entraînement par jour (7 derniers jours)
        volume_data = Performance.objects.filter(client=client) \
            .annotate(day=TruncDate('date_enregistrement')) \
            .values('day') \
            .annotate(
                total_volume=Sum(
                    ExpressionWrapper(
                        F('poids_utilise') * F('reps_realisees') * F('series_realisees'),
                        output_field=FloatField()
                    )
                )
            ).order_by('day')[:7]

        # 2. Répartition par catégorie de muscle
        muscle_data = Performance.objects.filter(client=client) \
            .values(name=F('seance_exercice__exercice__categorie')) \
            .annotate(value=Sum('reps_realisees')) \
            .order_by('-value')

        # 3. Formatage pour le Frontend
        formatted_volume = [
            {
                "day": entry['day'].strftime('%a') if entry['day'] else "N/A",
                "volume": entry['total_volume'] or 0
            } for entry in volume_data
        ]

        return Response({
            "volume_history": formatted_volume,
            "muscle_distribution": list(muscle_data),
            "summary": {
                "total_sessions": Performance.objects.filter(client=client).values('seance_exercice__seance').distinct().count(),
                "total_reps": Performance.objects.filter(client=client).aggregate(Sum('reps_realisees'))['reps_realisees__sum'] or 0
            }
        })

# --- AUTRES VUES ---

class CoachAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Coach requis"}, status=403)
        coach = request.user.coach_profile
        return Response({"total_athletes": coach.clients.count(), "total_volume": 0})

class PerformanceCreateView(generics.CreateAPIView):
    serializer_class = PerformanceSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        perf = serializer.save(client=self.request.user.client_profile)
        seance = perf.seance_exercice.seance
        if not seance.est_completee:
            seance.est_completee = True
            seance.save()

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

class CoachCalendarView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, coach_id):
        coach = get_object_or_404(Coach, id=coach_id)
        seances = Seance.objects.filter(coach=coach)
        data = [{"id": s.id, "title": s.titre, "start": str(s.jour_prevu)} for s in seances]
        return Response(data)

class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Indisponibilite.objects.filter(coach=self.request.user.coach_profile) if hasattr(self.request.user, 'coach_profile') else Indisponibilite.objects.none()

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_inscription_status(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    ins.statut = request.data.get('statut')
    ins.save()
    return Response({"status": "ok"})

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_participant(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    ins.delete()
    return Response(status=204)

@api_view(['GET'])
@permission_classes([AllowAny])
def export_coach_calendar(request, coach_id):
    return HttpResponse("Flux iCal en construction", content_type="text/calendar")

class DemoStatsView(APIView):
    permission_classes = [AllowAny]
def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(username=email, password=password)

        if user is None:
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        # DÉTECTION DU ROLE
        if hasattr(user, 'coach_profile'):
            role = 'coach'
        elif hasattr(user, 'client_profile'):
            role = 'athlete'
        else:
            role = 'prospect'

        return Response({
            "token": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "role": role
            }
        })

    def get(self, request):
        return Response({"total_exercices": Exercice.objects.count(), "total_coachs": Coach.objects.count()})


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Sécurité : Un coach ne voit QUE ses propres notifications
        if hasattr(self.request.user, 'coach_profile'):
            return Notification.objects.filter(coach=self.request.user.coach_profile)
        return Notification.objects.none()

    @action(detail=False, methods=['POST'])
    def marquer_tout_lu(self, request):
        # Cette fonction sera appelée quand le coach cliquera sur "Tout marquer comme lu"
        notifications = self.get_queryset().filter(est_lu=False)
        notifications.update(est_lu=True)
        return Response({'status': 'Toutes les notifications ont été marquées comme lues', 'count': notifications.count()})