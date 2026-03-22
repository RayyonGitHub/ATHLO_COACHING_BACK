from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

def validate_non_negatif(value):
    if value <= 0:
        raise ValidationError("Cette valeur doit être supérieure à 0.")
    
def validate_date_pas_dans_le_futur(value):
    if value and value > timezone.now().date():
        raise ValidationError("La date de naissance ne peut pas être dans le futur.")

# --- Modèles Profils ---

class Coach(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile')
    telephone = models.CharField(max_length=15, verbose_name="Téléphone", blank=True)
    
    specialites_tags = models.JSONField(default=list, blank=True) 
    offres_tarifs = models.JSONField(default=dict, blank=True)
    
    specialite = models.CharField(max_length=100, blank=True) 

    def __str__(self):
        return f"{self.user.username} - Coach"

class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile', null=True, blank=True)
    onboarding_data = models.JSONField(default=dict, blank=True)
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='clients', null=True, blank=True)
    
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20, blank=True)
    date_naissance = models.DateField(null=True, blank=True, validators=[validate_date_pas_dans_le_futur])
    age = models.PositiveIntegerField(null=True, blank=True)
    
    taille = models.PositiveIntegerField(null=True, blank=True, validators=[validate_non_negatif], help_text="Taille en cm")
    poids = models.FloatField(null=True, blank=True, validators=[validate_non_negatif], help_text="Poids en kg")

    objectifs_sportifs = models.TextField(blank=True, help_text="Objectif du client")
    pathologies_blessures = models.TextField(blank=True, help_text="Historique médical")
    
    consentement_rgpd = models.BooleanField(default=False, verbose_name="Consentement RGPD")
    est_archive = models.BooleanField(default=False, verbose_name="Archivé")
    tags = models.CharField(max_length=50, default="Standard", blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"

class Exercice(models.Model):
    CATEGORIES = [
        ('FORCE', 'Force & Musculation'),
        ('CARDIO', 'Cardio & Endurance'),
        ('SOUPLESSE', 'Souplesse & Mobilité'),
        ('ALTERO', 'Haltérophilie'),
        ('GYM', 'Gymnastique / Poids de corps')
    ]
    nom = models.CharField(max_length=150, unique=True, verbose_name="Nom de l'exercice")
    description = models.TextField(blank=True, verbose_name="Description et consignes")
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='FORCE')
    muscle_principal = models.CharField(max_length=100, blank=True, help_text="Ex: Pectoraux, Quadriceps...")
    video_url = models.URLField(blank=True, null=True, help_text="Lien YouTube ou démo")
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} ({self.get_categorie_display()})"

class Programme(models.Model):
    titre = models.CharField(max_length=200, verbose_name="Titre du programme")
    description = models.TextField(blank=True)
    
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='programmes_crees')
    athlete = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='programmes_assignes', null=True, blank=True)
    
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        nom_athlete = f"{self.athlete.prenom} {self.athlete.nom}" if self.athlete else "Aucun"
        return f"{self.titre} (Coach: {self.coach.user.username} -> Athlète: {nom_athlete})"

class Seance(models.Model):
    # 1. Lien direct avec le coach (obligatoire pour filtrer le calendrier du coach)
    coach = models.ForeignKey('Coach', on_delete=models.CASCADE, related_name='seances_creees')
    
    # 2. Le programme devient optionnel (pour les cours collectifs ou RDV ponctuels)
    programme = models.ForeignKey('Programme', on_delete=models.CASCADE, related_name='seances', null=True, blank=True)
    
    titre = models.CharField(max_length=150, verbose_name="Titre de la séance (ex: Haut du corps)")
    
    # --- INFOS CALENDRIER ---
    jour_prevu = models.DateField(null=True, blank=True, help_text="Date exacte si planifié dans le calendrier")
    heure_debut = models.TimeField(null=True, blank=True, help_text="Heure de début") 
    heure_fin = models.TimeField(null=True, blank=True, help_text="Heure de fin") 
    
    ordre = models.PositiveIntegerField(default=1, help_text="Jour 1, Jour 2, etc. (utile si dans un programme)")
    
    # --- PARAMÈTRES DE RÉSERVATION ---
    est_collective = models.BooleanField(default=False, verbose_name="Séance de groupe") 
    capacite_max = models.PositiveIntegerField(default=1, help_text="Nombre max de participants") 
    
    # --- SUIVI ---
    est_completee = models.BooleanField(default=False)
    commentaire_coach = models.TextField(blank=True, help_text="Notes du coach après la séance")
    ressenti_client = models.PositiveIntegerField(null=True, blank=True, help_text="Note de difficulté de 1 à 10 laissée par l'athlète")
    notes_client = models.TextField(blank=True, help_text="Commentaires de l'athlète")

    class Meta:
        ordering = ['jour_prevu', 'heure_debut', 'ordre']

    def clean(self):
        # Vérification pour l'affichage correct dans le calendrier
        if self.heure_debut and self.heure_fin:
            if self.heure_fin <= self.heure_debut:
                raise ValidationError("L'heure de fin doit être après l'heure de début.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        type_s = "Collectif" if self.est_collective else "Individuel"
        date_str = f"{self.jour_prevu} de {self.heure_debut} à {self.heure_fin}" if self.jour_prevu and self.heure_debut else f"Ordre: {self.ordre}"
        return f"{date_str} - {self.titre} ({type_s})"

    def calculer_volume_total(self):
        """ Calcule le tonnage total soulevé durant la séance """
        total = 0
        exercices = self.exercices_details.all()
        for exo in exercices:
            try:
                poids_str = "".join(filter(lambda x: x.isdigit() or x == '.', str(exo.poids)))
                poids_val = float(poids_str) if poids_str else 0
                rep_str = str(exo.repetitions).split('-')[0]
                rep_val = int("".join(filter(str.isdigit, rep_str)))
                total += exo.series * rep_val * poids_val
            except (ValueError, IndexError):
                continue
        return total

    @property
    def volume_total(self):
        return self.calculer_volume_total()

class SeanceExercice(models.Model):
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE, related_name='exercices_details')
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE)
    
    series = models.PositiveIntegerField(default=3)
    repetitions = models.CharField(max_length=50, default="10", help_text="ex: 10, 8-12, ou Temps (ex: 45s)")
    poids = models.CharField(max_length=50, blank=True, null=True, help_text="ex: 20kg, ou Poids du corps")
    repos = models.CharField(max_length=50, default="60s", help_text="Temps de repos")
    
    ordre = models.PositiveIntegerField(default=1, help_text="Ordre de l'exercice dans la séance")

    class Meta:
        ordering = ['ordre']

    def __str__(self):
        return f"{self.exercice.nom} - {self.series}x{self.repetitions}"

# --- NOUVEAU MODÈLE : ISSUE #14 (Tracking de Performance) ---

class Performance(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='performances')
    seance_exercice = models.ForeignKey(SeanceExercice, on_delete=models.CASCADE, related_name='performances')
    
    series_realisees = models.PositiveIntegerField(default=0)
    reps_realisees = models.PositiveIntegerField(default=0)
    poids_utilise = models.FloatField(default=0.0)
    
    notes_athlete = models.TextField(blank=True, null=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_enregistrement']

    def __str__(self):
        return f"Perf de {self.client.prenom} - {self.seance_exercice.exercice.nom}"
    
class Inscription(models.Model):
    STATUT_CHOICES = [
        ('CONFIRME', 'Confirmé'),
        ('ATTENTE', 'En liste d\'attente'),
        ('ANNULE', 'Annulé'),
        ('PRESENT', 'Présent'),
        ('ABSENT', 'Absent')


    ]
    
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE, related_name='inscriptions')
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='CONFIRME')
    date_inscription = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seance', 'client')

    def clean(self):
        # On ne vérifie la capacité que si l'on essaie de CONFIRMER une inscription
        if self.statut == 'CONFIRME':
            
            # On compte combien d'inscrits sont DÉJÀ confirmés.
            # Le .exclude(pk=self.pk) est crucial : il évite de se compter soi-même 
            # si on est en train de modifier une inscription existante.
            inscrits_confirmes = self.seance.inscriptions.filter(statut='CONFIRME').exclude(pk=self.pk).count()

            # 1. Règle pour séance individuelle (capacité forcée à 1)
            if not self.seance.est_collective:
                if inscrits_confirmes >= 1:
                    raise ValidationError("Cette séance individuelle est déjà réservée.")

            # 2. Règle pour séance collective (selon capacite_max)
            else:
                if inscrits_confirmes >= self.seance.capacite_max:
                    raise ValidationError(
                        f"La capacité maximale ({self.seance.capacite_max}) est atteinte. "
                        "L'inscription doit être mise en 'Liste d'attente'."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client.prenom} {self.client.nom} - {self.seance.titre} ({self.get_statut_display()})"
    
class Indisponibilite(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='indisponibilites')
    titre = models.CharField(max_length=100, default="Indisponible")
    
    # --- ON UTILISE LE MÊME FORMAT QUE LES SÉANCES ---
    jour_prevu = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    # ------------------------------------------------
    
    est_conge = models.BooleanField(default=False, help_text="Cochez si c'est un congé/vacances")

    def clean(self):
        # On vérifie juste que l'heure de fin est après l'heure de début
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            raise ValidationError("L'heure de fin doit être strictement postérieure à l'heure de début.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.coach.user.username} - {self.titre} ({self.jour_prevu.strftime('%d/%m/%Y')})"