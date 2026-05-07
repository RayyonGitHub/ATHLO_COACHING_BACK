from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
# Importe les modèles de la boutique
from .models import Recette, PlanNutritionnel, Produit, CategorieProduit 
from .serializers_nutrition import RecetteSerializer, PlanNutritionnelSerializer

class RecetteViewSet(viewsets.ModelViewSet):
    serializer_class = RecetteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            return Recette.objects.filter(coach=self.request.user.coach_profile)
        except:
            return Recette.objects.none()

    def perform_create(self, serializer):
        serializer.save(coach=self.request.user.coach_profile)


class PlanNutritionnelViewSet(viewsets.ModelViewSet):
    serializer_class = PlanNutritionnelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # CAS 1 : C'est le Coach
        if hasattr(user, 'coach_profile'):
            return PlanNutritionnel.objects.filter(coach=user.coach_profile)
            
        # CAS 2 : C'est l'Athlète
        if hasattr(user, 'client_profile'):
            athlete = user.client_profile
            
            # On cherche toutes les lignes de commande de cet athlète
            # appartenant à une commande qui est "PAYEE"
            lignes_payees = athlete.commandes.filter(
                status='PAID'
            ).values_list('lignes__produit_id', flat=True)
            print(f"DEBUG: Produits achetés par l'athlète : {list(lignes_payees)}") # <--- Ajoute ça
            
            # On renvoie les plans dont le "produit" fait partie des produits achetés
            return PlanNutritionnel.objects.filter(produit_id__in=lignes_payees)
            
        # Si aucun profil, on renvoie rien
        return PlanNutritionnel.objects.none()

    def perform_create(self, serializer):
        coach = self.request.user.coach_profile
        
        # 1. On prépare la catégorie "Nutrition"
        categorie, _ = CategorieProduit.objects.get_or_create(
            nom="Nutrition", 
            defaults={'slug': 'nutrition'}
        )
        
        # 2. On crée le produit Boutique EN PREMIER pour pouvoir le lier au plan
        produit_boutique = Produit.objects.create(
            coach=coach,
            nom=serializer.validated_data.get('titre'),
            description=serializer.validated_data.get('description') or f"Plan nutritionnel : {serializer.validated_data.get('titre')}",
            prix=serializer.validated_data.get('prix'),
            categorie=categorie,
            image=serializer.validated_data.get('image'), # On passe l'image ici pour la boutique
            type_produit='NUMERIQUE', # Produit dématérialisé
            stock=999,
            est_actif=True
        )
        
        # 3. On sauvegarde le plan en lui injectant le coach ET le produit créé
        serializer.save(coach=coach, produit=produit_boutique)