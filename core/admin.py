from django.contrib import admin
from .models import Coach, Client, Exercice, Programme, Seance, SeanceExercice,Inscription

# Profils
admin.site.register(Coach)
admin.site.register(Client)

# Sport (Exercices, Programmes et Séances)
admin.site.register(Exercice)
admin.site.register(Programme)
admin.site.register(Seance)
admin.site.register(SeanceExercice)
admin.site.register(Inscription)