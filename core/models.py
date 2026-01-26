from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

# --- Validateurs (le travail de ton collègue) ---
def validate_non_negatif(value):
    if value <= 0:
        raise ValidationError("Cette valeur doit être supérieure à 0.")
    
def validate_date_pas_dans_le_futur(value):
    if value and value > timezone.now().date():
        raise ValidationError("La date de naissance ne peut pas être dans le futur.")

# --- Modèles ---

class Coach(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile')
    specialite = models.CharField(max_length=100, verbose_name="Spécialité", blank=True)
    telephone = models.CharField(max_length=15, verbose_name="Téléphone", blank=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.user.username})"

class Client(models.Model):
    # Relation (Ton travail)
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='clients')
    
    # Identité (Fusionné avec les validateurs du collègue)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20, blank=True)
    date_naissance = models.DateField(null=True, blank=True, validators=[validate_date_pas_dans_le_futur])

    # Données physiologiques (Validées)
    taille = models.PositiveIntegerField(null=True, blank=True, validators=[validate_non_negatif], help_text="Taille en cm")
    poids = models.FloatField(null=True, blank=True, validators=[validate_non_negatif], help_text="Poids en kg")

    # Infos sportives et médicales
    objectifs_sportifs = models.TextField(blank=True, help_text="Objectif du client")
    pathologies_blessures = models.TextField(blank=True, help_text="Historique médical")
    
    # Suivi et RGPD
    consentement_rgpd = models.BooleanField(default=False, verbose_name="Consentement RGPD")
    est_archive = models.BooleanField(default=False, verbose_name="Archivé")
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"