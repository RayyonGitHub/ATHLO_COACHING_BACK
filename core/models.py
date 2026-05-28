from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.db.models import F
from django.dispatch import receiver
from django.core.validators import FileExtensionValidator, MinValueValidator
import uuid

# --- Validateurs ---
def validate_non_negatif(value):
    if value <= 0:
        raise ValidationError("Cette valeur doit être supérieure à 0.")

def validate_date_pas_dans_le_futur(value):
    if value and value > timezone.now().date():
        raise ValidationError("La date de naissance ne peut pas être dans le futur.")

# --- Modèles Profils ---
class Coach(models.Model):
    PLAN_CHOICES = [
        ('free', 'Gratuit (Freemium)'),
        ('premium', 'Premium (Abonnement)')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile')
    
    # --- Champs Stripe & Abonnement ---
    platform_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True, help_text="ID du compte Stripe Connect du coach")
    stripe_onboarding_complete = models.BooleanField(default=False)
    # ----------------------------------
    
    telephone = models.CharField(max_length=15, verbose_name="Téléphone", blank=True)
    specialites_tags = models.JSONField(default=list, blank=True)
    offres_tarifs = models.JSONField(default=dict, blank=True)
    specialite = models.CharField(max_length=100, blank=True)
    ville = models.CharField(max_length=100, blank=True)
    salles = models.ManyToManyField('Salle', related_name='coachs_affilies', blank=True)
    google_access_token = models.TextField(blank=True, null=True)
    google_refresh_token = models.TextField(blank=True, null=True)
    google_token_expires_at = models.DateTimeField(blank=True, null=True)
    def __str__(self):
        return f"{self.user.username} - Coach"


class Client(models.Model):
    seances_restantes = models.IntegerField(default=0)
    GENRE_CHOICES = [('M', 'Homme'), ('F', 'Femme'), ('O', 'Autre')]
    ACTIVITE_CHOICES = [
        ('1.2', 'Sédentaire (Bureau, peu de sport)'),
        ('1.375', 'Légèrement actif (Sport 1-3 j/semaine)'),
        ('1.55', 'Modérément actif (Sport 3-5 j/semaine)'),
        ('1.725', 'Très actif (Sport 6-7 j/semaine)'),
        ('1.9', 'Extrêmement actif (Athlète / Travail physique)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
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
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, default='M')
    niveau_activite = models.CharField(max_length=10, choices=ACTIVITE_CHOICES, default='1.55')
    poids_cible = models.FloatField(null=True, blank=True, help_text="Poids visé par l'athlète")
    type_entrainement = models.CharField(max_length=50, default='Musculation', help_text="Ex: Force, Cardio, Crossfit")
    notifications_activees = models.BooleanField(default=True, verbose_name="Notifications par mail")
    objectifs_sportifs = models.TextField(blank=True, help_text="Objectif du client")
    pathologies_blessures = models.TextField(blank=True, help_text="Historique médical")
    consentement_rgpd = models.BooleanField(default=False, verbose_name="Consentement RGPD")
    est_archive = models.BooleanField(default=False, verbose_name="Archivé")
    tags = models.CharField(max_length=50, default="Standard", blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    # --- NOUVEAUX CHAMPS : Intégrations Sportives (Strava & Garmin) ---
    strava_access_token = models.TextField(blank=True, null=True)
    strava_refresh_token = models.TextField(blank=True, null=True)
    strava_token_expires_at = models.DateTimeField(blank=True, null=True)
    strava_athlete_id = models.CharField(max_length=100, blank=True, null=True)

    garmin_access_token = models.TextField(blank=True, null=True)
    garmin_refresh_token = models.TextField(blank=True, null=True)
    garmin_token_expires_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.prenom} {self.nom}"

    @property
    def contrat_actif(self):
        today = timezone.now().date()
        abonnement = self.contrats.filter(
            statut='ACTIF',
            type_contrat='ABONNEMENT',
            date_debut__lte=today,
            date_expiration__gte=today,
        ).order_by('-date_expiration', '-id').first()
        if abonnement:
            return abonnement
        return self.contrats.filter(
            statut='ACTIF',
            type_contrat__in=['PACK', 'UNITE'],
            seances_restantes__gt=0,
        ).order_by('date_debut', 'id').first()

    @property
    def abonnement_valide(self):
        today = timezone.now().date()
        return self.contrats.filter(
            type_contrat='ABONNEMENT',
            statut='ACTIF',
            date_debut__lte=today,
            date_expiration__gte=today
        ).exists()

    @property
    def peut_reserver_seance(self):
        return self.abonnement_valide or (self.seances_restantes or 0) > 0


class ContratAthlete(models.Model):
    TYPE_CHOICES = [
        ('ABONNEMENT', 'Abonnement mensuel'),
        ('PACK', 'Pack de seances'),
        ('UNITE', 'Seance a l unite'),
    ]
    STATUT_CHOICES = [
        ('ACTIF', 'Actif'),
        ('EXPIRE', 'Expire'),
        ('ANNULE', 'Annule'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contrats')
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='contrats_athletes')
    type_contrat = models.CharField(max_length=20, choices=TYPE_CHOICES)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='ACTIF')
    date_debut = models.DateField(default=timezone.now)
    date_expiration = models.DateField(null=True, blank=True)
    seances_total = models.PositiveIntegerField(default=0)
    seances_restantes = models.PositiveIntegerField(default=0)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    montant_ttc = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut', '-id']

    @property
    def est_valide(self):
        if self.statut != 'ACTIF':
            return False
        if self.type_contrat == 'ABONNEMENT':
            return bool(self.date_expiration and self.date_expiration >= timezone.now().date())
        return self.seances_restantes > 0

    def __str__(self):
        return f"{self.client} - {self.type_contrat}"


# --- Invitation paiement client créé par coach ---
class ClientInvitation(models.Model):
    OFFER_TYPES = [
        ('seance', 'Séance unique'),
        ('pack', 'Pack 10 séances'),
        ('abonnement', 'Abonnement mensuel'),
    ]
    STATUS_CHOICES = [
        ('pending', 'En attente de paiement'),
        ('paid', 'Payé'),
        ('activated', 'Activé'),
        ('expired', 'Expiré'),
        ('cancelled', 'Annulé'),
    ]

    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='client_invitations')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='payment_invitations')
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPES, default='abonnement')
    offer_label = models.CharField(max_length=100, default='Abonnement mensuel')
    amount = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, default='pending')
    card_last4 = models.CharField(max_length=4, blank=True)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Invitation {self.client} - {self.offer_label}"


# --- Sport & Séances ---
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
class Salle(models.Model):
    nom = models.CharField(max_length=150)
    adresse = models.CharField(max_length=255)
    ville = models.CharField(max_length=100)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    coachs_bannis = models.ManyToManyField('Coach', related_name='salles_bannies', blank=True)

class Programme(models.Model):
    titre = models.CharField(max_length=200, verbose_name="Titre du programme")
    description = models.TextField(blank=True)
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='programmes_crees')
    athlete = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='programmes_assignes', null=True, blank=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titre

class ResponsableSalle(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='responsable_profile')
    salle = models.ForeignKey(Salle, on_delete=models.CASCADE, related_name='responsables')
    telephone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} - Responsable {self.salle.nom}"
    
class Seance(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='seances_creees')
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name='seances', null=True, blank=True)
    salle = models.ForeignKey(Salle, on_delete=models.SET_NULL, related_name='seances', null=True, blank=True)
    titre = models.CharField(max_length=150, verbose_name="Titre de la séance")
    jour_prevu = models.DateField(null=True, blank=True)
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)
    ordre = models.PositiveIntegerField(default=1)
    est_collective = models.BooleanField(default=False)
    capacite_max = models.PositiveIntegerField(default=1)
    est_completee = models.BooleanField(default=False)
    commentaire_coach = models.TextField(blank=True)
    ressenti_client = models.PositiveIntegerField(null=True, blank=True)
    notes_client = models.TextField(blank=True)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
 
    class Meta:
        ordering = ['jour_prevu', 'heure_debut', 'ordre']


class SeanceExercice(models.Model):
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE, related_name='exercices_details')
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE)
    series = models.PositiveIntegerField(default=3)
    repetitions = models.CharField(max_length=50, default="10")
    poids = models.CharField(max_length=50, blank=True, null=True)
    repos = models.CharField(max_length=50, default="60s")
    ordre = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['ordre']


class Performance(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='performances')
    seance_exercice = models.ForeignKey(SeanceExercice, on_delete=models.CASCADE, related_name='performances')
    series_realisees = models.PositiveIntegerField(default=0)
    reps_realisees = models.PositiveIntegerField(default=0)
    poids_utilise = models.FloatField(default=0.0)
    notes_athlete = models.TextField(blank=True, null=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)


class Inscription(models.Model):
    STATUT_CHOICES = [
        ('CONFIRME', 'Confirmé'),
        ('ATTENTE', 'Liste d\'attente'),
        ('ANNULE', 'Annulé'),
        ('PRESENT', 'Présent'),
        ('ABSENT', 'Absent')
    ]
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE, related_name='inscriptions')
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='CONFIRME')
    date_inscription = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seance', 'client')

    def clean(self):
        super().clean()
        if self.statut in ['CONFIRME', 'PRESENT', 'ABSENT']:
            inscrits_confirmes = Inscription.objects.filter(
                seance=self.seance,
                statut__in=['CONFIRME', 'PRESENT', 'ABSENT']
            ).exclude(pk=self.pk).count()
            
            if inscrits_confirmes >= self.seance.capacite_max:
                raise ValidationError(
                    f"La capacité maximale ({self.seance.capacite_max} participants) est atteinte. Impossible de confirmer cette inscription."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Indisponibilite(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='indisponibilites')
    titre = models.CharField(max_length=100, default="Indisponible")
    jour_prevu = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    est_conge = models.BooleanField(default=False)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
    
class Avis(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='avis')
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    note = models.IntegerField()
    commentaire = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    TYPES = [
        ('INSCRIPTION', 'Inscription'),
        ('DESINSCRIPTION', 'Désinscription'),
        ('ANNULATION', 'Annulation'),
        ('MODIFICATION', 'Modification'),
        ('INFO', 'Information'),
        ('PAIEMENT', 'Paiement'),
    ]
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    seance = models.ForeignKey(Seance, on_delete=models.SET_NULL, null=True, blank=True)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPES, default='INFO')
    est_lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)


# --- MESSAGERIE ---
class Conversation(models.Model):
    CONVERSATION_TYPES = [('direct', 'Directe'), ('group', 'Groupe')]
    conversation_type = models.CharField(max_length=20, choices=CONVERSATION_TYPES, default='direct')
    title = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-created_at']

class ConversationParticipant(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_conversations')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('conversation', 'user')

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

def message_attachment_upload_path(instance, filename):
    return f"messages/conversation_{instance.message.conversation.id}/{filename}"

class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(
        upload_to=message_attachment_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'doc', 'docx', 'txt'])]
    )
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class NotificationAthlete(models.Model):
    TYPES = [
        ('SEANCE', 'Séance'),
        ('RAPPEL', 'Rappel'),
        ('OBJECTIF', 'Objectif'),
        ('INFO', 'Information')
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='notifications_athlete', null=True, blank=True)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPES, default='INFO')
    est_lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']


class NotificationResponsable(models.Model):
    TYPES = [
        ('SEANCE', 'Séance'),
        ('COACH', 'Coach'),
        ('SALLE', 'Salle'),
        ('URGENT', 'Urgent'),
        ('INFO', 'Information')
    ]
    responsable = models.ForeignKey('ResponsableSalle', on_delete=models.CASCADE, related_name='notifications_responsable')
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPES, default='INFO')
    est_lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']


@receiver(post_save, sender=Seance)
def inscrire_athlete_du_programme(sender, instance, created, **kwargs):
    if not created:
        return
    if not instance.programme_id:
        return
    athlete = getattr(instance.programme, 'athlete', None)
    if not athlete:
        return
    if not (instance.jour_prevu and instance.heure_debut):
        return
    if not athlete.peut_reserver_seance:
        raise ValidationError("Quota de séances atteint pour cet athlète.")
        
    inscription, nouvelle = Inscription.objects.get_or_create(
        seance=instance,
        client=athlete,
        defaults={'statut': 'CONFIRME'}
    )
    if nouvelle:
        if not athlete.abonnement_valide:
            contrat = athlete.contrats.filter(statut='ACTIF', type_contrat__in=['PACK', 'UNITE'], seances_restantes__gt=0).order_by('date_debut', 'id').first()
            if contrat:
                contrat.seances_restantes = F('seances_restantes') - 1
                contrat.save(update_fields=['seances_restantes'])
            athlete.seances_restantes = F('seances_restantes') - 1
            athlete.save(update_fields=['seances_restantes'])
        NotificationAthlete.objects.create(
            client=athlete,
            message=f"Tu as été inscrit(e) à la séance : {instance.titre}",
            type='SEANCE'
        )


# Notification au responsable de salle quand une séance est créée pour sa salle
@receiver(post_save, sender=Seance)
def notify_responsable_on_seance_created(sender, instance, created, **kwargs):
    if not created:
        return
    if not instance.salle:
        return

    # Trouver le responsable de la salle (s'il existe)
    responsables = instance.salle.responsables.all()
    for resp in responsables:
        Notification.objects.create(
            coach=None,
            seance=instance,
            message=(f"Nouvelle séance planifiée: #{instance.id} - {instance.titre} "
                     f"le {instance.jour_prevu} à {instance.heure_debut or 'heure non précisée'}"),
            type='INFO'
        )


class Devis(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
    ]
    OFFRE_CHOICES = [
        ('seance', 'Séance individuelle'),
        ('pack', 'Pack'),
        ('abonnement', 'Abonnement'),
    ]

    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='devis')
    prospect = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='devis_demandes')
    offre_type = models.CharField(max_length=20, choices=OFFRE_CHOICES, default='seance')
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    age = models.IntegerField(null=True, blank=True)
    taille = models.IntegerField(null=True, blank=True)
    poids = models.FloatField(null=True, blank=True)
    niveau_activite = models.CharField(max_length=50, blank=True)
    type_entrainement = models.CharField(max_length=50, blank=True)
    objectif_sportif = models.TextField(blank=True)
    budget = models.CharField(max_length=50, blank=True)
    pathologies_blessures = models.TextField(blank=True)
    message = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="en_attente")
    prix_propose = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    invitation_liee = models.ForeignKey(
        ClientInvitation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devis_associes'
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.coach}"


# --- Données Sportives Importées (Strava / Garmin) ---
class ActiviteExterne(models.Model):
    PLATEFORMES = [
        ('STRAVA', 'Strava'),
        ('GARMIN', 'Garmin')
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='activites_externes')
    plateforme = models.CharField(max_length=20, choices=PLATEFORMES)
    external_id = models.CharField(max_length=255, unique=True, help_text="ID unique de l'activité sur Strava/Garmin")
    
    nom = models.CharField(max_length=255, help_text="Titre de l'activité (ex: Course matinale)")
    type_activite = models.CharField(max_length=100, help_text="Run, Ride, Swim, Workout...")
    date_debut = models.DateTimeField()
    
    distance_metres = models.FloatField(null=True, blank=True)
    temps_secondes = models.FloatField(null=True, blank=True)
    calories = models.FloatField(null=True, blank=True)
    frequence_cardiaque_moyenne = models.FloatField(null=True, blank=True)
    
    donnees_brutes = models.JSONField(default=dict, blank=True, help_text="Stocke toute la réponse brute de l'API au cas où")
    date_import = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut']

    def __str__(self):
        return f"{self.nom} - {self.plateforme} ({self.client.prenom} {self.client.nom})"


class CategorieProduit(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = "Catégorie de Produit"
        verbose_name_plural = "Catégories de Produits"

    def __str__(self):
        return self.nom


class Produit(models.Model):
    TYPE_CHOICES = [
        ('PHYSIQUE', 'Produit Physique'),
        ('NUMERIQUE', 'Produit Numérique (PDF, etc.)'),
    ]
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='produits_boutique')
    nom = models.CharField(max_length=200)
    description = models.TextField()
    prix = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    # ICI : On pointe bien vers le modèle CategorieProduit
    categorie = models.ForeignKey('CategorieProduit', on_delete=models.SET_NULL, null=True, related_name='produits')
    type_produit = models.CharField(max_length=20, choices=TYPE_CHOICES, default='PHYSIQUE')
    
    # Gestion des stocks
    stock = models.PositiveIntegerField(default=0)
    est_actif = models.BooleanField(default=True)
    
    # Logistique
    peut_etre_livre = models.BooleanField(default=True)
    peut_etre_retire = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nom} (par {self.coach.user.username})"


class Commande(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'), 
        ('PAID', 'Payée'), 
        ('FAILED', 'Échouée'),
        ('EXPEDIEE', 'Expédiée'),
        ('LIVREE', 'Livrée'),
        ('ANNULEE', 'Annulée'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='commandes')
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='ventes', null=True, blank=True)
    order_number = models.CharField(max_length=40, unique=True, default=uuid.uuid4)
    
    # Détails de l'offre (Stripe / Prospect)
    offre_label = models.CharField(max_length=150, blank=True, null=True)
    offre_type = models.CharField(max_length=50, blank=True, null=True) # 'seance', 'pack', 'abonnement'
    
    # Financier
    montant_ht = models.FloatField(default=0.0)
    tva_taux = models.FloatField(default=20.0)
    montant_ttc = models.FloatField(default=0.0)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    date_commande = models.DateTimeField(auto_now_add=True)
    
    # Référence Stripe
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)

    # Logistique (Boutique)
    adresse_livraison = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Commande {self.order_number} - {self.client}"


class LigneCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField(default=1)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom}"
    
    # --- MODULE NUTRITION ---

class Recette(models.Model):
    CATEGORIE_CHOICES = [
        ('Petit-déjeuner', 'Petit-déjeuner'),
        ('Déjeuner', 'Déjeuner'),
        ('Dîner', 'Dîner'),
        ('Collation', 'Collation'),
        ('Pre-workout', 'Pre-workout'),
    ]
    
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='recettes')
    nom = models.CharField(max_length=200)
    type = models.CharField(max_length=50, choices=CATEGORIE_CHOICES, default='Petit-déjeuner')
    
    # Macros nutritionnels
    calories = models.PositiveIntegerField(default=0)
    proteines = models.PositiveIntegerField(default=0)
    glucides = models.PositiveIntegerField(default=0)
    lipides = models.PositiveIntegerField(default=0)
    
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} ({self.coach.user.username})"


class PlanNutritionnel(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='plans_nutritionnels')
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    image = models.ImageField(upload_to='plans_nutrition/', null=True, blank=True)
    
    # La fameuse table de liaison créée automatiquement par Django !
    recettes = models.ManyToManyField(Recette, related_name='plans')
    
    # Lien vers la boutique : on relie le plan à un produit numérique
    produit = models.OneToOneField(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name='plan_source')
    
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Plan: {self.titre} ({self.coach.user.username})"


class Facture(models.Model):
    commande = models.OneToOneField(Commande, on_delete=models.CASCADE, related_name='facture')
    numero_facture = models.CharField(max_length=50, unique=True)
    date_emission = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='factures/', blank=True, null=True)

    def __str__(self):
        return f"Facture {self.numero_facture}"

    def save(self, *args, **kwargs):
        if not self.numero_facture:
            self.numero_facture = f"FAC-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"
        
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            from .invoice_utils import generate_invoice_pdf
            generate_invoice_pdf(self)
            super().save(update_fields=['pdf_file'])
