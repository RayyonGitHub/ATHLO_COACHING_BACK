import json
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Commande, Facture, ClientInvitation, Notification, Coach


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse(status=400)

    event_dict = json.loads(payload)

    # 1. Gestion des paiements des ATHLÈTES (achats, invitations)
    if event_dict['type'] == 'payment_intent.succeeded':
        intent = event_dict['data']['object']
        metadata = intent.get('metadata', {})
        checkout_type = metadata.get('checkout_type')

        if checkout_type == 'shop_order':
            commande_id = metadata.get('commande_id')
            try:
                commande = Commande.objects.get(id=commande_id)
                if commande.status != 'PAID':
                    commande.status = 'PAID'
                    commande.stripe_payment_intent_id = intent.get('id')
                    commande.save()
                    Facture.objects.get_or_create(commande=commande)
            except Commande.DoesNotExist:
                pass

        elif checkout_type == 'invitation':
            token = metadata.get('invitation_token')
            invitation = ClientInvitation.objects.filter(token=token).first()
            if invitation and invitation.status == 'pending':
                invitation.status = 'paid'
                invitation.payment_status = 'success'
                invitation.paid_at = timezone.now()
                invitation.save()
                
                Notification.objects.create(
                    coach=invitation.coach,
                    seance=None,
                    type='PAIEMENT',
                    message=f"Paiement confirmé via invitation pour {invitation.client.prenom} ({invitation.amount}€)."
                )

    # 2. Gestion de l'abonnement PREMIUM DU COACH (Nouveau)
    elif event_dict['type'] == 'checkout.session.completed':
        session = event_dict['data']['object']
        metadata = session.get('metadata', {})
        
        if metadata.get('checkout_type') == 'platform_subscription':
            coach_id = metadata.get('coach_id')
            try:
                coach = Coach.objects.get(id=coach_id)
                coach.platform_plan = 'premium'
                coach.stripe_subscription_id = session.get('subscription')
                coach.save()
            except Coach.DoesNotExist:
                pass

    # 3. Annulation de l'abonnement du coach (Downgrade vers free)
    elif event_dict['type'] == 'customer.subscription.deleted':
        subscription = event_dict['data']['object']
        try:
            coach = Coach.objects.get(stripe_subscription_id=subscription.get('id'))
            coach.platform_plan = 'free'
            coach.stripe_subscription_id = None
            coach.save()
        except Coach.DoesNotExist:
            pass

    return HttpResponse(status=200)
class CreatePlatformSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        coach = request.user.coach_profile
        
        # 1. Créer le customer Stripe s'il n'existe pas
        if not coach.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                name=f"{request.user.first_name} {request.user.last_name}"
            )
            coach.stripe_customer_id = customer.id
            coach.save()

        try:
            # 2. Création de la session Checkout en mode 'subscription'
            checkout_session = stripe.checkout.Session.create(
                customer=coach.stripe_customer_id,
                payment_method_types=['card'],
                mode='subscription',
                line_items=[{
                    # ATTENTION : Remplace ce 'price_xxx' par ton VRAI ID de prix Stripe !
                    'price': getattr(settings, 'STRIPE_PREMIUM_PRICE_ID', 'price_1TXkjbC9OZTHr1sPOvQJsjwl'), 
                    'quantity': 1,
                }],
                metadata={
                    'checkout_type': 'platform_subscription',
                    'coach_id': coach.id
                },
                success_url=settings.FRONTEND_URL + '/coach/settings?session_id={CHECKOUT_SESSION_ID}&success=true',
                cancel_url=settings.FRONTEND_URL + '/coach/settings?canceled=true',
            )
            return Response({'checkout_url': checkout_session.url})
        except Exception as e:
            print(f"❌ ERREUR STRIPE ABONNEMENT : {str(e)}") # S'affichera dans ton terminal
            return Response({'error': str(e)}, status=400)


class CreateStripeConnectAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        coach = request.user.coach_profile
        front_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        
        # 1. Si le coach n'a pas encore de compte Connect créé
        if not coach.stripe_account_id:
            try:
                # Version ultra-simplifiée : on laisse Stripe gérer le reste
                account = stripe.Account.create(
                    type="express",
                    email=request.user.email if request.user.email else None,
                )
                coach.stripe_account_id = account.id
                coach.save()
            except Exception as e:
                print(f"❌ ERREUR CREATION COMPTE CONNECT : {str(e)}") # S'affichera dans ton terminal
                return Response({'error': str(e)}, status=400)

        # 2. On crée un lien d'onboarding sécurisé vers Stripe
        try:
            account_link = stripe.AccountLink.create(
                account=coach.stripe_account_id,
                refresh_url=f"{front_url}/coach/settings?stripe_connect=refresh",
                return_url=f"{front_url}/coach/settings?stripe_connect=success",
                type="account_onboarding",
            )
            return Response({'checkout_url': account_link.url})
        except Exception as e:
            print(f"❌ ERREUR LIEN ONBOARDING CONNECT : {str(e)}") # S'affichera dans ton terminal
            return Response({'error': str(e)}, status=400)