from rest_framework import viewsets, status
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import Client, Coach
from .serializers import ClientSerializer, CoachSerializer 

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Un coach ne voit QUE ses propres clients
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def perform_create(self, serializer):
        # Attribution automatique du coach connecté
        try:
            coach_profile = self.request.user.coach_profile
            serializer.save(coach=coach_profile)
        except Coach.DoesNotExist:
            raise PermissionDenied("Vous n'avez pas de profil Coach associé.")

# Vue pour l'onboarding et le profil du coach (Issue #F2)
# Elle gère la route /api/coach/me/ appelée par le front
class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Utilise get_or_create pour éviter la 404 si le coach se connecte pour la première fois
        coach, created = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach)
        return Response(serializer.data)

    def patch(self, request):
        # get_or_create élimine le risque d'AttributeError et donc la 403
        coach, created = Coach.objects.get_or_create(user=request.user)
        
        # Le serializer va maintenant pouvoir enregistrer 'specialites_tags' et 'offres_tarifs'
        serializer = CoachSerializer(coach, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        # En cas d'erreur (ex: mauvais format de données), on renvoie les détails (400)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class AthleteMeView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        # On récupère le client lié à l'user. 
        # Si absent, on le crée avec les infos de base de l'User
        client, created = Client.objects.get_or_create(
            user=request.user,
            defaults={
                'email': request.user.email,
                'nom': request.user.last_name,
                'prenom': request.user.first_name
            }
        )
        
        # On passe partial=True pour ne mettre à jour que ce qu'on reçoit
        serializer = ClientSerializer(client, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        
        return Response(serializer.errors, status=400)