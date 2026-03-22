# core/apps.py
from django.apps import AppConfig
import os

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # On importe les signaux pour s'assurer qu'ils sont bien chargés
        try:
            import core.models
        except ImportError:
            pass

        # Cette condition évite que Django lance le minuteur 2 fois (à cause de son système de rechargement)
        if os.environ.get('RUN_MAIN') == 'true':
            from apscheduler.schedulers.background import BackgroundScheduler
            from .tasks import generer_rappels_automatiques

            # On crée un minuteur qui tourne en arrière-plan
            scheduler = BackgroundScheduler()
            
            # On lui dit d'exécuter la fonction toutes les 1 minute
            # (En production on mettrait 'hours=1', mais pour tester 1 minute c'est parfait)
            scheduler.add_job(generer_rappels_automatiques, 'interval', minutes=1)
            
            scheduler.start()
            print(" [SYSTEM] Le moteur de rappels automatiques est lancé (Vérification toutes les 60s)...")