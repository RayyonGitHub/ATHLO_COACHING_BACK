from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Produit, CategorieProduit
from .serializers import ProduitSerializer, CategorieProduitSerializer

class ProduitViewSet(viewsets.ModelViewSet):
    """
    Gestion des produits : 
    - Les coachs gèrent leurs propres produits.
    - Les athlètes voient tous les produits actifs.
    """
    serializer_class = ProduitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Si c'est un coach, il voit son inventaire personnel
        if hasattr(user, 'coach_profile'):
            return Produit.objects.filter(coach=user.coach_profile)
        
        # Si c'est un athlète, il voit TOUS les produits actifs
        return Produit.objects.filter(est_actif=True)

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            return Response(
                {"detail": "Seuls les coachs peuvent créer des produits."}, 
                status=status.HTTP_403_FORBIDDEN
            )

class CategorieProduitViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Simple vue pour permettre au front de lister les catégories.
    """
    queryset = CategorieProduit.objects.all()
    serializer_class = CategorieProduitSerializer 
    permission_classes = [permissions.IsAuthenticated]