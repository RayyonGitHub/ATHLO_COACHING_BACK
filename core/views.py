from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import Client, Coach
from .serializers import ClientSerializer

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated] # Sécurité : faut être connecté

    def get_queryset(self):
        # Un coach ne voit QUE ses propres clients
        # Si l'utilisateur n'est pas un coach, on renvoie une liste vide ou erreur
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def perform_create(self, serializer):
        # C'est ici la MAGIE : on remplit le champ 'coach' automatiquement
        try:
            coach_profile = self.request.user.coach_profile
            serializer.save(coach=coach_profile)
        except Coach.DoesNotExist:
            raise PermissionDenied("Vous n'avez pas de profil Coach associé.")