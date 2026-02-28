from django.contrib.auth.models import User
from rest_framework import viewsets, status
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser,AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Client, Coach, Exercice, Programme, Seance
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer

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
# --- VUE DÉMO 

class DemoStatsView(APIView):
    permission_classes = [AllowAny] 

    def get(self, request):
        data = {
            "total_exercices": Exercice.objects.count(),
            "total_coachs": Coach.objects.count(),
            "utilisateurs_actifs": User.objects.count(),
            # Maintenant que le modèle existe, on peut utiliser le vrai count
            "programmes_crees": Programme.objects.count(), 
            "message": "Ceci est une démo. Connectez-vous pour accéder à votre suivi personnalisé."
        }
        return Response(data)

# --- NOUVELLES VUES 

class ExerciceViewSet(viewsets.ModelViewSet):
    queryset = Exercice.objects.all()
    serializer_class = ExerciceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly] # On garde ta permission plus souple
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

class AthleteDashboardView(APIView):
    """ Renvoie toutes les infos condensées pour la page d'accueil de l'athlète """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
            
        client = user.client_profile

        # Trouver la prochaine séance non complétée
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