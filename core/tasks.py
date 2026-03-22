# core/tasks.py
from datetime import date
from .models import Seance, Notification

def generer_rappels_automatiques():
    """
    Cherche UNIQUEMENT les séances d'AUJOURD'HUI et envoie un rappel.
    """
    # On prend la date locale exacte de ton ordinateur (infaillible)
    aujourd_hui = date.today()

    # On cherche les séances prévues pour aujourd'hui qui ne sont pas finies
    seances_a_venir = Seance.objects.filter(
        jour_prevu=aujourd_hui,
        est_completee=False
    )

    for seance in seances_a_venir:
        # On vérifie si la cloche n'a pas DÉJÀ sonné pour ce rappel
        rappel_existe = Notification.objects.filter(
            seance=seance,
            type='RAPPEL'
        ).exists()

        if not rappel_existe:
            heure_texte = seance.heure_debut.strftime('%H:%M')

            Notification.objects.create(
                coach=seance.coach,
                seance=seance,
                type='RAPPEL',
                message=f"⏰ Rappel : Ta séance '{seance.titre}' a lieu aujourd'hui à {heure_texte}."
            )
            print(f"[AUTO] Rappel généré pour la séance du jour : {seance.titre}")