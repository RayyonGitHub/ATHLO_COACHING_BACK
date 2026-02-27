from rest_framework import viewsets, status
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated
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
        return Response(serializer.errors, status=400)


# --- NOUVELLES VUES (Issue #9 et #10) ---

class ExerciceViewSet(viewsets.ModelViewSet):
    queryset = Exercice.objects.all()
    serializer_class = ExerciceSerializer
    permission_classes = [IsAuthenticated]

class ProgrammeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgrammeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Si c'est un coach, il voit les programmes qu'il a créés
        if hasattr(user, 'coach_profile'):
            return Programme.objects.filter(coach=user.coach_profile)
        # Si c'est un athlète, il voit les programmes qu'on lui a assignés
        elif hasattr(user, 'client_profile'):
            return Programme.objects.filter(athlete=user.client_profile)
        return Programme.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            raise PermissionDenied("Seuls les coachs peuvent créer un programme.")

# --- VUE SPÉCIALE DASHBOARD FRONT-END ---

class AthleteDashboardView(APIView):
    """ Renvoie toutes les infos condensées pour la page d'accueil de l'athlète """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
            
        client = user.client_profile

        # 1. Trouver la prochaine séance non complétée
        prochaine_seance = Seance.objects.filter(
            programme__athlete=client,
            est_completee=False
        ).order_by('jour_prevu', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            # On calcule des stats fictives basées sur le nombre d'exercices
            nb_exos = prochaine_seance.exercices_details.count()
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "programme_titre": prochaine_seance.programme.titre,
                "duree_estimee": nb_exos * 10 if nb_exos > 0 else 45, # 10 min par exo
                "calories_estimees": nb_exos * 80 if nb_exos > 0 else 450,
            }

        # 2. On prépare le gros JSON pour ton Front-end
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