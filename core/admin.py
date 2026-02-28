from django.contrib import admin
from .models import Coach, Client, Exercice, Programme, Seance, SeanceExercice

# On garde tes enregistrements existants
admin.site.register(Coach)
admin.site.register(Client)
admin.site.register(Exercice)

# On ajoute les nouveaux modèles sportifs
admin.site.register(Programme)
admin.site.register(Seance)
admin.site.register(SeanceExercice)