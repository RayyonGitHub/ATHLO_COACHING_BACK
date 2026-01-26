from django.db import models
from django.contrib.auth.models import User

# Modèle pour le Coach (lié à un compte utilisateur Django)
class Coach(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile')
    specialite = models.CharField(max_length=100, verbose_name="Spécialité", blank=True)
    telephone = models.CharField(max_length=15, verbose_name="Téléphone", blank=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.user.username})"

# Modèle pour l'Athlète (Client)
class Athlete(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, verbose_name="Coach référent", related_name='athletes')
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    date_naissance = models.DateField(null=True, blank=True)
    poids = models.FloatField(help_text="Poids en kg", null=True, blank=True)
    taille = models.IntegerField(help_text="Taille en cm", null=True, blank=True)
    objectif = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"