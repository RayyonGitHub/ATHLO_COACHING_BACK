import json
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Commande, Facture, ClientInvitation, Notification

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        # 1. Vérification sécurisée de la signature par Stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Payload invalide
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Signature invalide
        return HttpResponse(status=400)

    # 2. Conversion du payload brut en VRAI dictionnaire Python (100% sûr)
    event_dict = json.loads(payload)

    # Si le paiement est réussi...
    if event_dict['type'] == 'payment_intent.succeeded':
        intent = event_dict['data']['object']
        
        # Maintenant ce sont de vrais dictionnaires, .get() fonctionne parfaitement !
        metadata = intent.get('metadata', {})
        checkout_type = metadata.get('checkout_type')

        # Cas 1 : Achat dans la boutique (Option 2)
        if checkout_type == 'shop_order':
            commande_id = metadata.get('commande_id')
            try:
                commande = Commande.objects.get(id=commande_id)
                if commande.status != 'PAID':
                    commande.status = 'PAID'
                    commande.stripe_payment_intent_id = intent.get('id')
                    commande.save()
                    # Génération automatique de la facture en PDF
                    Facture.objects.get_or_create(commande=commande)
            except Commande.DoesNotExist:
                pass

        # Cas 2 : Paiement via invitation coach (Option 1)
        elif checkout_type == 'invitation':
            token = metadata.get('invitation_token')
            invitation = ClientInvitation.objects.filter(token=token).first()
            if invitation and invitation.status == 'pending':
                invitation.status = 'paid'
                invitation.payment_status = 'success'
                invitation.paid_at = timezone.now()
                invitation.save()
                
                # On notifie le coach
                Notification.objects.create(
                    coach=invitation.coach,
                    seance=None,
                    type='PAIEMENT',
                    message=f"Paiement confirmé via invitation pour {invitation.client.prenom} ({invitation.amount}€)."
                )

    return HttpResponse(status=200)