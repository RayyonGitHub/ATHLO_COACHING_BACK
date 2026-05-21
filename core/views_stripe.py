import json
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Commande, Facture, ClientInvitation, Notification, Coach

stripe.api_key = settings.STRIPE_SECRET_KEY


def stripe_connect_relay(request):
    """Relay view: redirects to mobile deep link or web frontend after Stripe flows."""
    platform = request.GET.get('platform', 'web')
    status = request.GET.get('status', 'success')

    if platform == 'mobile':
        expo_dev_url = getattr(settings, 'EXPO_DEV_URL', None)
        if expo_dev_url:
            target = f"{expo_dev_url}/--/(tabs)/coach/settings?stripe_connect={status}"
        else:
            target = f"athlo://(tabs)/coach/settings?stripe_connect={status}"
        # Use raw HttpResponse to bypass Django's scheme whitelist (exp:// is safe here)
        response = HttpResponse(status=302)
        response['Location'] = target
        return response

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    return redirect(f"{frontend_url}/parametres?stripe_connect={status}")


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
    # 4. Vérification de la complétion du compte Stripe Connect
    elif event_dict['type'] == 'account.updated':
        account = event_dict['data']['object']
        if account.get('details_submitted') == True:
            try:
                coach = Coach.objects.get(stripe_account_id=account.get('id'))
                if not coach.stripe_onboarding_complete:
                    coach.stripe_onboarding_complete = True
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

        platform = request.data.get('platform', 'web')
        front_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

        if platform == 'mobile':
            backend_url = request.build_absolute_uri('/').rstrip('/')
            success_url = f"{backend_url}/api/stripe/connect-relay/?platform=mobile&status=subscription_success"
            cancel_url = f"{backend_url}/api/stripe/connect-relay/?platform=mobile&status=subscription_canceled"
        else:
            success_url = front_url + '/parametres?session_id={CHECKOUT_SESSION_ID}&success=true'
            cancel_url = front_url + '/parametres?canceled=true'

        try:
            checkout_session = stripe.checkout.Session.create(
                customer=coach.stripe_customer_id,
                payment_method_types=['card'],
                mode='subscription',
                line_items=[{
                    'price': getattr(settings, 'STRIPE_PREMIUM_PRICE_ID', 'price_1TXkjbC9OZTHr1sPOvQJsjwl'),
                    'quantity': 1,
                }],
                metadata={
                    'checkout_type': 'platform_subscription',
                    'coach_id': coach.id
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return Response({'checkout_url': checkout_session.url})
        except Exception as e:
            print(f"❌ ERREUR STRIPE ABONNEMENT : {str(e)}")
            return Response({'error': str(e)}, status=400)


class CheckStripeConnectStatusView(APIView):
    """Call this after returning from Stripe onboarding to sync stripe_onboarding_complete."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        coach = request.user.coach_profile

        if not coach.stripe_account_id:
            return Response({'stripe_onboarding_complete': False})

        try:
            account = stripe.Account.retrieve(coach.stripe_account_id)
            if account.details_submitted and not coach.stripe_onboarding_complete:
                coach.stripe_onboarding_complete = True
                coach.save(update_fields=['stripe_onboarding_complete'])
        except Exception as e:
            print(f"❌ ERREUR connect-status : {str(e)}")
            return Response({'error': str(e)}, status=400)

        return Response({'stripe_onboarding_complete': coach.stripe_onboarding_complete})


class CreateStripeConnectAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        coach = request.user.coach_profile
        front_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        platform = request.data.get('platform', 'web')

        # Build relay URLs for mobile, direct URLs for web
        if platform == 'mobile':
            backend_url = request.build_absolute_uri('/').rstrip('/')
            return_url = f"{backend_url}/api/stripe/connect-relay/?platform=mobile&status=success"
            refresh_url = f"{backend_url}/api/stripe/connect-relay/?platform=mobile&status=refresh"
        else:
            return_url = f"{front_url}/parametres?stripe_connect=success"
            refresh_url = f"{front_url}/parametres?stripe_connect=refresh"

        # 1. Si le coach n'a pas encore de compte Connect créé
        if not coach.stripe_account_id:
            try:
                account = stripe.Account.create(
                    type="express",
                    email=request.user.email if request.user.email else None,
                )
                coach.stripe_account_id = account.id
                coach.save()
            except Exception as e:
                print(f"❌ ERREUR CREATION COMPTE CONNECT : {str(e)}")
                return Response({'error': str(e)}, status=400)

        # 2. On crée un lien d'onboarding sécurisé vers Stripe
        try:
            account_link = stripe.AccountLink.create(
                account=coach.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
            )
            return Response({'checkout_url': account_link.url})
        except Exception as e:
            print(f"❌ ERREUR LIEN ONBOARDING CONNECT : {str(e)}")
            return Response({'error': str(e)}, status=400)