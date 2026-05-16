import stripe
from django.conf import settings
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Produit, CategorieProduit, Commande, LigneCommande
from .serializers import ProduitSerializer, CategorieProduitSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY

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

class CategorieProduitViewSet(viewsets.ModelViewSet): # On change ReadOnlyModelViewSet par ModelViewSet
    """
    Vue pour lister et CRÉER les catégories depuis le front.
    """
    queryset = CategorieProduit.objects.all()
    serializer_class = CategorieProduitSerializer 
    permission_classes = [permissions.IsAuthenticated]


class CreateShopPaymentIntentView(APIView):
    """
    Création de l'intention de paiement Stripe pour le panier de la boutique
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"error": "Seul un athlète peut faire des achats."}, status=403)

        items = request.data.get('items', [])
        if not items:
            return Response({"error": "Votre panier est vide."}, status=400)

        total_amount = 0
        
        try:
            # On récupère le coach à partir du premier produit du panier
            premier_produit = Produit.objects.get(id=items[0]['id'])
        except Produit.DoesNotExist:
            return Response({"error": "Produit introuvable."}, status=404)

        # 1. On crée une commande en statut PENDING en attachant le coach
        commande = Commande.objects.create(
            client=request.user.client_profile,
            coach=premier_produit.coach,
            offre_label="Achat Boutique",
            offre_type="shop",
            status='PENDING'
        )
        
        # 2. On ajoute les produits (Lignes de commande)
        for item in items:
            produit = Produit.objects.get(id=item['id'])
            quantite = int(item['quantite'])
            prix = float(produit.prix)
            total_amount += prix * quantite
            
            LigneCommande.objects.create(
                commande=commande,
                produit=produit,
                quantite=quantite,
                prix_unitaire=prix
            )

        # Sauvegarde des montants finaux
        commande.montant_ttc = total_amount
        commande.montant_ht = round(total_amount / 1.2, 2)
        commande.save()

        # 3. Création de l'intention Stripe liée à cette Commande
        fee_amount = 0
        if premier_produit.coach.platform_plan == 'free':
            fee_amount = int((total_amount * 100) * 0.10) # 10% de commission

        intent_kwargs = {
            "amount": int(total_amount * 100),
            "currency": 'eur',
            "metadata": {
                'checkout_type': 'shop_order',
                'commande_id': commande.id,
            }
        }

        # Transfert de l'argent au coach si un compte Stripe Connect est configuré
        if premier_produit.coach.stripe_account_id:
            intent_kwargs["application_fee_amount"] = fee_amount
            intent_kwargs["transfer_data"] = {
                "destination": premier_produit.coach.stripe_account_id
            }

        intent = stripe.PaymentIntent.create(**intent_kwargs)

        return Response({"client_secret": intent.client_secret}, status=200)