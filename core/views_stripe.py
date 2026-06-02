import json
import logging
import stripe
import time
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Commande, Facture, ClientInvitation, Notification, NotificationAthlete, Coach, Client
from .views_shop import mark_shop_order_paid
from .contract_utils import grant_session_contract, grant_subscription_contract

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

ATHLETE_TOPUP_LABELS = {
    'seance': 'Seance supplementaire',
    'pack': 'Pack 10 seances',
    'abonnement': 'Renouvellement abonnement',
}

ATHLETE_TOPUP_CREDITS = {
    'seance': 1,
    'pack': 10,
    'abonnement': 0,
}

ATHLETE_TOPUP_TYPES = {
    'seance': 'UNITE',
    'pack': 'PACK',
    'abonnement': 'ABONNEMENT',
}


def _normalize_offres(raw_offres):
    defaults = {'seance': 60, 'pack': 500, 'abonnement': 180}
    if isinstance(raw_offres, str):
        try:
            raw_offres = json.loads(raw_offres)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_offres = {}
    if not isinstance(raw_offres, dict):
        return defaults
    normalized = defaults.copy()
    for key in normalized:
        try:
            normalized[key] = float(raw_offres.get(key, defaults[key]))
        except (TypeError, ValueError):
            normalized[key] = defaults[key]
    return normalized


def _stripe_object_to_dict(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, 'to_dict_recursive'):
        return value.to_dict_recursive()
    if hasattr(value, '_data') and isinstance(value._data, dict):
        return dict(value._data)
    return {}


def _grant_athlete_topup_from_intent(intent):
    metadata = _stripe_object_to_dict(intent.get('metadata') if isinstance(intent, dict) else getattr(intent, 'metadata', None))
    if metadata.get('checkout_type') != 'athlete_topup':
        return None

    payment_intent_id = intent.get('id') if isinstance(intent, dict) else getattr(intent, 'id', None)
    client_id = metadata.get('client_id')
    coach_id = metadata.get('coach_id')
    offer_type = metadata.get('offer_type')
    credits = int(metadata.get('credits') or ATHLETE_TOPUP_CREDITS.get(offer_type, 0))
    amount_cents = intent.get('amount', 0) if isinstance(intent, dict) else getattr(intent, 'amount', 0)
    amount = float(amount_cents or 0) / 100

    if not payment_intent_id or offer_type not in ATHLETE_TOPUP_TYPES:
        return None

    with transaction.atomic():
        athlete = Client.objects.select_for_update().select_related('coach', 'user').get(id=client_id)
        existing = Commande.objects.filter(stripe_payment_intent_id=payment_intent_id).first()
        if existing:
            return existing

        commande = Commande.objects.create(
            client=athlete,
            coach_id=coach_id or athlete.coach_id,
            offre_label=ATHLETE_TOPUP_LABELS.get(offer_type, 'Achat seances'),
            offre_type=offer_type,
            montant_ttc=amount,
            montant_ht=round(amount / 1.2, 2),
            status='PAID',
            stripe_payment_intent_id=payment_intent_id,
        )
        Facture.objects.get_or_create(commande=commande)

        if offer_type == 'abonnement':
            grant_subscription_contract(
                athlete,
                athlete.coach,
                amount,
                payment_intent_id=payment_intent_id,
            )
        else:
            grant_session_contract(
                athlete,
                athlete.coach,
                ATHLETE_TOPUP_TYPES[offer_type],
                credits,
                amount,
                payment_intent_id=payment_intent_id,
            )

        if athlete.coach_id:
            Notification.objects.create(
                coach=athlete.coach,
                seance=None,
                type='PAIEMENT',
                message=f"Paiement confirme pour {athlete.prenom} {athlete.nom} : {commande.offre_label} ({amount:.2f} EUR)."
            )
        NotificationAthlete.objects.create(
            client=athlete,
            type='INFO',
            message=f"Contrat active : {commande.offre_label}."
        )
        return commande


def _grant_athlete_topup_from_intent_with_retry(intent, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            return _grant_athlete_topup_from_intent(intent)
        except OperationalError as error:
            last_error = error
            if "database is locked" not in str(error).lower() or attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))
    raise last_error


def _mark_shop_order_paid_with_retry(commande, payment_intent_id, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            return mark_shop_order_paid(commande, payment_intent_id)
        except OperationalError as error:
            last_error = error
            if "database is locked" not in str(error).lower() or attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))
    raise last_error


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

    frontend_url = settings.FRONTEND_URL
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
                    _mark_shop_order_paid_with_retry(commande, intent.get('id'))
            except Commande.DoesNotExist:
                logger.warning("stripe_webhook: commande introuvable", extra={"commande_id": commande_id})
            except OperationalError as e:
                if "database is locked" in str(e).lower():
                    logger.warning("stripe_webhook: database locked sur commande boutique, Stripe doit retenter", extra={"commande_id": commande_id, "error": str(e)})
                    return HttpResponse(status=500)
                logger.exception("stripe_webhook: confirmation boutique impossible", extra={"error": str(e)})
            except Exception as e:
                logger.exception("stripe_webhook: confirmation boutique impossible", extra={"error": str(e)})

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

        elif checkout_type == 'athlete_topup':
            try:
                _grant_athlete_topup_from_intent_with_retry(intent)
            except OperationalError as e:
                if "database is locked" in str(e).lower():
                    logger.warning("stripe_webhook: database locked, Stripe doit retenter", extra={"error": str(e)})
                    return HttpResponse(status=500)
                logger.exception("stripe_webhook: athlete_topup impossible", extra={"error": str(e)})
            except Exception as e:
                logger.exception("stripe_webhook: athlete_topup impossible", extra={"error": str(e)})

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
                logger.warning("stripe_webhook: coach introuvable pour subscription", extra={"coach_id": coach_id})

    # 3. Annulation de l'abonnement du coach (Downgrade vers free)
    elif event_dict['type'] == 'customer.subscription.deleted':
        subscription = event_dict['data']['object']
        try:
            coach = Coach.objects.get(stripe_subscription_id=subscription.get('id'))
            coach.platform_plan = 'free'
            coach.stripe_subscription_id = None
            coach.save()
        except Coach.DoesNotExist:
            logger.warning(
                "stripe_webhook: coach introuvable pour suppression abonnement",
                extra={"subscription_id": subscription.get('id')}
            )
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
                logger.warning(
                    "stripe_webhook: coach introuvable pour account.updated",
                    extra={"stripe_account_id": account.get('id')}
                )

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
        front_url = settings.FRONTEND_URL

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


class CreateAthleteTopUpPaymentIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        athlete = getattr(request.user, 'client_profile', None)
        if not athlete or not athlete.coach:
            return Response({"message": "Profil athlete ou coach introuvable."}, status=400)

        offer_type = (request.data.get('offer_type') or '').strip().lower()
        if offer_type not in ATHLETE_TOPUP_CREDITS:
            return Response({"message": "Type d'offre invalide."}, status=400)

        coach = athlete.coach
        if not coach.stripe_account_id or not coach.stripe_onboarding_complete:
            return Response({"message": "Le coach n'a pas configure ses paiements."}, status=400)

        offres = _normalize_offres(coach.offres_tarifs)
        amount = float(offres.get(offer_type) or 0)
        if amount <= 0:
            return Response({"message": "Prix de l'offre invalide."}, status=400)

        active_contract = athlete.contrat_actif
        if active_contract:
            if active_contract.type_contrat == 'ABONNEMENT' and offer_type != 'abonnement':
                return Response({
                    "message": f"Votre abonnement est actif jusqu'au {active_contract.date_expiration.strftime('%d/%m/%Y')}. Vous pourrez acheter des seances apres cette date."
                }, status=400)
            if active_contract.type_contrat in ['PACK', 'UNITE'] and offer_type == 'abonnement':
                return Response({
                    "message": "Vous avez deja des seances actives. Vous pourrez passer a l'abonnement quand elles seront terminees."
                }, status=400)

        try:
            fee_amount = int((amount * 100) * 0.10) if coach.platform_plan == 'free' else 0
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),
                currency='eur',
                automatic_payment_methods={"enabled": True},
                application_fee_amount=fee_amount,
                transfer_data={"destination": coach.stripe_account_id},
                metadata={
                    'checkout_type': 'athlete_topup',
                    'client_id': str(athlete.id),
                    'coach_id': str(coach.id),
                    'offer_type': offer_type,
                    'offer_label': ATHLETE_TOPUP_LABELS[offer_type],
                    'credits': str(ATHLETE_TOPUP_CREDITS[offer_type]),
                },
            )
            return Response({
                "client_secret": intent.client_secret,
                "offer": {
                    "type": offer_type,
                    "label": ATHLETE_TOPUP_LABELS[offer_type],
                    "price": amount,
                    "credits": ATHLETE_TOPUP_CREDITS[offer_type],
                },
            })
        except Exception as e:
            return Response({"message": str(e)}, status=400)


class ConfirmAthleteTopUpPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        athlete = getattr(request.user, 'client_profile', None)
        payment_intent_id = (request.data.get('payment_intent_id') or '').strip()
        if not athlete or not payment_intent_id:
            return Response({"message": "Donnees invalides."}, status=400)

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        except Exception:
            return Response({"message": "Paiement Stripe introuvable."}, status=400)

        metadata = _stripe_object_to_dict(getattr(intent, 'metadata', None))
        if intent.status != 'succeeded':
            return Response({"message": "Paiement non confirme."}, status=400)
        if metadata.get('checkout_type') != 'athlete_topup' or str(metadata.get('client_id')) != str(athlete.id):
            return Response({"message": "Paiement non autorise."}, status=403)

        try:
            commande = _grant_athlete_topup_from_intent_with_retry(intent)
        except ValidationError as err:
            detail = getattr(err, 'detail', None)
            message = detail.get('message') if isinstance(detail, dict) else "Changement de contrat impossible."
            return Response({"message": message}, status=400)
        athlete.refresh_from_db(fields=['seances_restantes'])
        contrat = athlete.contrat_actif
        return Response({
            "message": "Droits mis a jour.",
            "commande_id": commande.id if commande else None,
            "seances_restantes": athlete.seances_restantes,
            "contrat": {
                "type": contrat.type_contrat if contrat else None,
                "date_expiration": contrat.date_expiration if contrat else None,
                "seances_restantes": contrat.seances_restantes if contrat else athlete.seances_restantes,
            }
        })


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
        front_url = settings.FRONTEND_URL
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
