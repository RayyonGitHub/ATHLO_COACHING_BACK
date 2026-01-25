from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

# Create your models here.
def validate_non_negatif(value):
    if value <= 0:
        raise ValidationError("Cette valeur doit être supérieure à 0.")
    
def validate_date_pas_dans_le_futur(value):
    if value and value > timezone.now().date():
        raise ValidationError("La date de naissance ne peut pas être dans le futur.")
class Client(models.Model):
    #identité
    nom=models.CharField(max_length=100)
    prenom=models.CharField(max_length=100)
    date_naissance = models.DateField(null=True, blank=True, validators=[validate_date_pas_dans_le_futur], verbose_name="Date de naissance")
    email=models.EmailField(unique=True)
    telephone=models.CharField(max_length=20, blank=True)

    # Données physiologiques 
    taille = models.PositiveIntegerField(null=True, blank=True,validators=[validate_non_negatif], help_text="Taille en cm")
    poids = models.FloatField(null=True, blank=True,validators=[validate_non_negatif], help_text="Poids en kg")

    #Infos sportives et médicales
    objectifs_sportifs=models.TextField(help_text="Objectif du client (ex: perte de poids)")
    pathologies_blessures=models.TextField(blank=True, help_text="Historique des blessures / restrictions")
    
    #Segmentation
    tags=models.CharField(max_length=255, help_text="ex: premium, perte de poids")

    consentement_rgpd = models.BooleanField(
        default=False, 
        verbose_name="Consentement RGPD reçu",
        help_text="Le client a accepté le traitement de ses données sportives."
    )

    #Suivi et Archivage
    date_creation=models.DateTimeField(auto_now_add=True)
    est_archive=models.BooleanField(default=False, verbose_name="Client inactif / Dossier archivé")

    def __str__(self):
        return f"{self.prenom} {self.nom}"