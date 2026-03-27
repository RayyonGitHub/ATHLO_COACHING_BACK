from django.apps import AppConfig
import os

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        try:
            import core.models
            import core.google_signals
        except ImportError:
            pass

        if os.environ.get('RUN_MAIN') == 'true':
            from apscheduler.schedulers.background import BackgroundScheduler
            from .tasks import generer_rappels_automatiques

            scheduler = BackgroundScheduler()
            scheduler.add_job(generer_rappels_automatiques, 'interval', minutes=1)
            scheduler.start()
            print(" [SYSTEM] Le moteur de rappels automatiques est lancé (Vérification toutes les 60s)...")