from django.contrib import admin
from .models import Coach, Client, Exercice, Programme, Seance, SeanceExercice

# Profils
admin.site.register(Coach)
admin.site.register(Client)

admin.site.register(Exercice)
admin.site.register(Programme)
admin.site.register(Seance)
admin.site.register(SeanceExercice)
