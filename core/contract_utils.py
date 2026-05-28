from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Client, ContratAthlete


def sync_session_balance(client):
    total = client.contrats.filter(
        statut='ACTIF',
        type_contrat__in=['PACK', 'UNITE'],
        seances_restantes__gt=0,
    ).aggregate(total=Sum('seances_restantes'))['total'] or 0
    Client.objects.filter(id=client.id).update(seances_restantes=total)
    client.seances_restantes = total
    return total


def grant_subscription_contract(client, coach, amount, payment_intent_id=None):
    today = timezone.now().date()

    current_subscription = client.contrats.filter(
        type_contrat='ABONNEMENT',
        statut='ACTIF',
        date_expiration__gte=today
    ).order_by('-date_expiration').first()

    active_sessions = client.contrats.filter(
        statut='ACTIF',
        type_contrat__in=['PACK', 'UNITE'],
        seances_restantes__gt=0,
    ).exists()
    if active_sessions and not current_subscription:
        raise ValidationError({"message": "Vous avez deja des seances actives. Vous pourrez passer a l'abonnement quand elles seront terminees."})

    start_date = current_subscription.date_expiration + timedelta(days=1) if current_subscription else today

    return ContratAthlete.objects.create(
        client=client,
        coach=coach,
        type_contrat='ABONNEMENT',
        statut='ACTIF',
        date_debut=start_date,
        date_expiration=start_date + timedelta(days=30),
        seances_total=0,
        seances_restantes=0,
        stripe_payment_intent_id=payment_intent_id,
        montant_ttc=amount or 0,
    )


def grant_session_contract(client, coach, contrat_type, credits, amount, payment_intent_id=None):
    today = timezone.now().date()

    active_subscription = client.contrats.filter(
        statut='ACTIF',
        type_contrat='ABONNEMENT',
        date_expiration__gte=today,
    ).order_by('-date_expiration').first()
    if active_subscription:
        raise ValidationError({
            "message": f"Votre abonnement est actif jusqu'au {active_subscription.date_expiration.strftime('%d/%m/%Y')}. Vous pourrez acheter des seances apres cette date."
        })

    contrat = ContratAthlete.objects.create(
        client=client,
        coach=coach,
        type_contrat=contrat_type,
        statut='ACTIF',
        date_debut=today,
        seances_total=credits,
        seances_restantes=credits,
        stripe_payment_intent_id=payment_intent_id,
        montant_ttc=amount or 0,
    )
    sync_session_balance(client)
    return contrat
