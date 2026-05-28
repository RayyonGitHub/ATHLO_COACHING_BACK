import stripe
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Produit, CategorieProduit, Commande, LigneCommande, Facture, Notification, NotificationAthlete
from .serializers import ProduitSerializer, CategorieProduitSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY
SHIPPING_FEE = Decimal('4.00')


def _validate_shop_items(items):
    quantities_by_product = {}
    for item in items:
        try:
            product_id = int(item.get('id'))
            quantite = int(item.get('quantite'))
        except (TypeError, ValueError):
            raise ValueError("Panier invalide.")
        if quantite <= 0:
            raise ValueError("Quantité invalide.")
        quantities_by_product[product_id] = quantities_by_product.get(product_id, 0) + quantite
    normalized_items = [
        {"id": product_id, "quantite": quantite}
        for product_id, quantite in quantities_by_product.items()
    ]
    product_ids = list(quantities_by_product.keys())
    return normalized_items, product_ids


def mark_shop_order_paid(commande, payment_intent_id):
    with transaction.atomic():
        commande = Commande.objects.select_for_update().select_related('client', 'coach').get(id=commande.id)
        if commande.status == 'PAID':
            return commande

        lignes = commande.lignes.select_related('produit').select_for_update()
        for ligne in lignes:
            produit = ligne.produit
            if produit.type_produit == 'PHYSIQUE':
                produit_locked = Produit.objects.select_for_update().get(id=produit.id)
                if produit_locked.stock < ligne.quantite:
                    raise ValueError(f"Stock insuffisant pour {produit_locked.nom}.")
                produit_locked.stock = F('stock') - ligne.quantite
                produit_locked.save(update_fields=['stock'])

        commande.status = 'PAID'
        commande.stripe_payment_intent_id = payment_intent_id
        commande.save(update_fields=['status', 'stripe_payment_intent_id'])
        Facture.objects.get_or_create(commande=commande)

        produits_label = ", ".join(
            f"{ligne.quantite} x {ligne.produit.nom}"
            for ligne in commande.lignes.select_related('produit')
        )
        if commande.coach_id:
            Notification.objects.create(
                coach=commande.coach,
                type='PAIEMENT',
                message=f"Nouvel achat boutique par {commande.client.prenom} {commande.client.nom} : {produits_label}."
            )
        NotificationAthlete.objects.create(
            client=commande.client,
            type='INFO',
            message=f"Commande boutique confirmée : {produits_label}."
        )
        return commande

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

        try:
            normalized_items, product_ids = _validate_shop_items(items)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        total_amount = Decimal('0.00')
        
        try:
            # On récupère le coach à partir du premier produit du panier
            premier_produit = Produit.objects.select_related('coach').get(id=normalized_items[0]['id'], est_actif=True)
        except Produit.DoesNotExist:
            return Response({"error": "Produit introuvable."}, status=404)

        produits = {
            produit.id: produit
            for produit in Produit.objects.select_for_update().select_related('coach').filter(id__in=product_ids, est_actif=True)
        }
        if len(produits) != len(set(product_ids)):
            return Response({"error": "Un produit du panier est introuvable ou indisponible."}, status=400)
        if any(produit.coach_id != premier_produit.coach_id for produit in produits.values()):
            return Response({"error": "Un panier ne peut contenir que des produits du même coach."}, status=400)

        # 1. On crée une commande en statut PENDING en attachant le coach
        commande = Commande.objects.create(
            client=request.user.client_profile,
            coach=premier_produit.coach,
            offre_label="Achat Boutique",
            status='PENDING'
        )
        
        # 2. On ajoute les produits (Lignes de commande)
        for item in normalized_items:
            produit = produits[item['id']]
            quantite = item['quantite']
            if produit.type_produit == 'PHYSIQUE' and produit.stock < quantite:
                return Response({"error": f"Stock insuffisant pour {produit.nom}. Stock disponible : {produit.stock}."}, status=400)
            prix = produit.prix
            total_amount += prix * quantite
            
            LigneCommande.objects.create(
                commande=commande,
                produit=produit,
                quantite=quantite,
                prix_unitaire=prix
            )

        # Sauvegarde des montants finaux
        total_amount += SHIPPING_FEE
        commande.montant_ttc = float(total_amount)
        commande.montant_ht = round(float(total_amount) / 1.2, 2)
        commande.save()

        # 3. Création de l'intention Stripe liée à cette Commande
        fee_amount = 0
        if premier_produit.coach.platform_plan == 'free':
            fee_amount = int((total_amount * 100) * Decimal('0.10')) # 10% de commission

        intent_kwargs = {
            "amount": int(total_amount * 100),
            "currency": 'eur',
            "metadata": {
                'checkout_type': 'shop_order',
                'commande_id': str(commande.id),
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


class ShopOrderConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payment_intent_id = request.data.get('payment_intent_id')
        
        if not payment_intent_id:
            return Response({"error": "payment_intent_id requis"}, status=400)
        
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            if intent.status != 'succeeded':
                return Response({"error": "Paiement non confirmé"}, status=400)
            
            commande_id = intent.metadata.get('commande_id')
            if not commande_id:
                return Response({"error": "Commande introuvable dans les métadonnées"}, status=400)
            
            commande = Commande.objects.get(id=commande_id)
            if commande.client_id != request.user.client_profile.id:
                return Response({"error": "Commande non autorisée"}, status=403)
            
            if commande.status != 'PAID':
                mark_shop_order_paid(commande, payment_intent_id)
            
            return Response({"success": True, "commande_id": commande.id})
        
        except Commande.DoesNotExist:
            return Response({"error": "Commande introuvable"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
