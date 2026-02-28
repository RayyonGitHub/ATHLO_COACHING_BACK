from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import viewsets, status, generics # Ajout de generics ici
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework.exceptions import PermissionDenied

# Ajout de Performance et PerformanceSerializer
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer


# --- Vues Existantes ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def perform_create(self, serializer):
        try:
            coach_profile = self.request.user.coach_profile
            serializer.save(coach=coach_profile)
        except Coach.DoesNotExist:
            raise PermissionDenied("Vous n'avez pas de profil Coach associé.")

class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach)
        return Response(serializer.data)

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
            defaults={
                'email': request.user.email,
                'nom': request.user.last_name,
                'prenom': request.user.first_name
            }
        )
        serializer = ClientSerializer(client, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)


# --- VUE DÉMO ---

class DemoStatsView(APIView):
    permission_classes = [AllowAny] 

    def get(self, request):
        data = {
            "total_exercices": Exercice.objects.count(),
            "total_coachs": Coach.objects.count(),
            "utilisateurs_actifs": User.objects.count(),
            "programmes_crees": Programme.objects.count(), 
            "message": "Ceci est une démo. Connectez-vous pour accéder à votre suivi personnalisé."
        }
        return Response(data)


# --- NOUVELLES VUES SPORTIVES ---

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


# --- VUE POUR LE CRÉATEUR DE SÉANCE ---

class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(programme__coach=user.coach_profile)
        elif hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    @transaction.atomic 
    def create(self, request, *args, **kwargs):
        data = request.data
        programme_id = data.get('programme_id')
        titre = data.get('titre')
        exercices_data = data.get('exercices', [])

        if not programme_id or not titre:
            return Response({"error": "Le programme_id et le titre sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        programme = get_object_or_404(Programme, id=programme_id)

        if not hasattr(request.user, 'coach_profile') or programme.coach != request.user.coach_profile:
            raise PermissionDenied("Vous n'êtes pas autorisé à ajouter une séance à ce programme.")

        ordre_seance = Seance.objects.filter(programme=programme).count() + 1

        seance = Seance.objects.create(
            programme=programme,
            titre=titre,
            ordre=ordre_seance
        )

        for exo_data in exercices_data:
            exercice = get_object_or_404(Exercice, id=exo_data.get('exercice_id'))
            SeanceExercice.objects.create(
                seance=seance,
                exercice=exercice,
                series=exo_data.get('series', 3),
                repetitions=exo_data.get('repetitions', '10'),
                poids=exo_data.get('poids', 'Poids du corps'),
                repos=exo_data.get('repos', '60s'),
                ordre=exo_data.get('ordre', 1)
            )

        serializer = self.get_serializer(seance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# --- VUES ANALYTICS ET DASHBOARD ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
            
        client = user.client_profile

        prochaine_seance = Seance.objects.filter(
            programme__athlete=client,
            est_completee=False
        ).order_by('jour_prevu', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            nb_exos = prochaine_seance.exercices_details.count()
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "programme_titre": prochaine_seance.programme.titre,
                "duree_estimee": nb_exos * 10 if nb_exos > 0 else 45,
                "calories_estimees": nb_exos * 80 if nb_exos > 0 else 450,
            }

        data = {
            "prenom": client.prenom or user.username,
            "prochaine_seance": seance_data,
            "stats_sante": {
                "completion_jour": 75,
                "calories": 1840,
                "calories_max": 2400,
                "recuperation": 94,
            }
        }
        return Response(data)

    
class CoachAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Accès réservé aux coachs."}, status=403)
        
        coach = request.user.coach_profile
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6) 

        total_athletes = coach.clients.count()

        seances_7_jours = Seance.objects.filter(
            programme__coach=coach,
            jour_prevu__range=[seven_days_ago, today]
        )

        total_seances = seances_7_jours.count()
        seances_completees = seances_7_jours.filter(est_completee=True).count()

        completion_rate = 0
        if total_seances > 0:
            completion_rate = round((seances_completees / total_seances) * 100, 1)
        
        total_volume = seances_completees * 450
        
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
            "completion_rate": completion_rate,
            "total_volume": total_volume,  
            "chart_data": chart_data,
            "period": "7 derniers jours"
        })

# --- NOUVELLE VUE : ISSUE #14 (Enregistrement de Performance) ---

class PerformanceCreateView(generics.CreateAPIView):
    serializer_class = PerformanceSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # On lie automatiquement la performance au client connecté
        if hasattr(self.request.user, 'client_profile'):
            serializer.save(client=self.request.user.client_profile)
        else:
            raise PermissionDenied("Seul un athlète peut enregistrer une performance.")