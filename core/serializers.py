from rest_framework import serializers
import datetime
from django.utils import timezone
from django.db.models import Avg, Count
from .models import (
    ActiviteExterne, Client, Coach, Exercice, Programme, Seance, 
    SeanceExercice, Performance, Indisponibilite, 
    Inscription, Notification, NotificationAthlete, Salle, Avis, Devis,
)

# Cherchez la ligne "from .models import ..."
from .models import (
    Client, Coach, Produit, CategorieProduit,  # <-- AJOUTEZ CategorieProduit ICI
    Commande, LigneCommande
)
# --- PROFILS ---
class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['coach', 'user']

class CoachSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coach
        fields = ['id', 'specialites_tags', 'offres_tarifs', 'telephone', 'specialite', 'ville']


# --- SERIALIZER PUBLIC POUR LES PROSPECTS ---
class ProspectProgrammePreviewSerializer(serializers.ModelSerializer):
    duree = serializers.SerializerMethodField()

    class Meta:
        model = Programme
        fields = ['id', 'titre', 'duree']

    def get_duree(self, obj):
        nb = obj.seances.count()
        if nb <= 0:
            return "Programme"
        if nb == 1:
            return "1 séance"
        return f"{nb} séances"


class ProspectCoachSerializer(serializers.ModelSerializer):
    nom = serializers.SerializerMethodField()
    specialites = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()
    avis = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()
    tarifs = serializers.SerializerMethodField()
    programmes_gratuits = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Coach
        fields = [
            'id',
            'nom',
            'specialites',
            'note',
            'avis',
            'distance',
            'tarifs',
            'image',
            'ville',
            'specialite',
            'programmes_gratuits',
        ]

    def get_nom(self, obj):
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        if full_name:
            return full_name
        return obj.user.username or obj.user.email

    def get_specialites(self, obj):
        if obj.specialites_tags and isinstance(obj.specialites_tags, list):
            return obj.specialites_tags
        if obj.specialite:
            return [obj.specialite]
        return []

    def get_note(self, obj):
        avg = obj.avis.aggregate(moyenne=Avg('note'))['moyenne']
        if avg is None:
            return 0
        return round(float(avg), 1)

    def get_avis(self, obj):
        return obj.avis.count()

    def get_distance(self, obj):
        # Pas de vraie géolocalisation exploitable dans tes modèles pour l’instant.
        # On renvoie la ville si dispo pour éviter le statique mensonger.
        return obj.ville if obj.ville else "Ville non renseignée"

    def get_tarifs(self, obj):
        tarifs = obj.offres_tarifs if isinstance(obj.offres_tarifs, dict) else {}

        return {
            "seance": tarifs.get("seance", 0),
            "pack": tarifs.get("pack", 0),
            "abonnement": tarifs.get("abonnement", 0),
        }

    def get_programmes_gratuits(self, obj):
        programmes = obj.programmes_crees.all().order_by('-id')[:2]
        return ProspectProgrammePreviewSerializer(programmes, many=True).data

    def get_image(self, obj):
        return None
        
# --- SPORTIFS ---
class ExerciceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercice
        fields = '__all__'

class SeanceExerciceSerializer(serializers.ModelSerializer):
    exercice_details = ExerciceSerializer(source='exercice', read_only=True)

    class Meta:
        model = SeanceExercice
        fields = '__all__'

class InscriptionDetailsSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_id = serializers.ReadOnlyField(source='client.id')

    class Meta:
        model = Inscription
        fields = ['id', 'client_id', 'client_name', 'statut', 'date_inscription']

    def get_client_name(self, obj):
        return f"{obj.client.prenom} {obj.client.nom}".strip()

class SeanceSerializer(serializers.ModelSerializer):
    exercices = serializers.SerializerMethodField()
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()
    participants = InscriptionDetailsSerializer(source='inscriptions', many=True, read_only=True)
    nombre_inscrits = serializers.SerializerMethodField()
    places_restantes = serializers.SerializerMethodField()
    est_inscrit = serializers.SerializerMethodField()
    mon_statut = serializers.SerializerMethodField()

    class Meta:
        model = Seance
        fields = '__all__'
        read_only_fields = ['coach']

    def get_nombre_inscrits(self, obj):
        if not hasattr(obj, 'inscriptions'):
            return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()

    def get_places_restantes(self, obj):
        if not obj.capacite_max:
            return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)

    def get_exercices(self, obj):
        from .models import SeanceExercice
        exos = SeanceExercice.objects.filter(seance=obj).order_by('ordre')
        return [
            {
                "id": e.id,
                "exercice_id": e.exercice.id if e.exercice else None,
                "nom": e.exercice.nom if e.exercice else "Exercice inconnu",
                "series": e.series,
                "repetitions": e.repetitions,
                "poids": e.poids,
                "repos": e.repos,
                "ordre": e.ordre
            } for e in exos
        ]

    def get_est_inscrit(self, obj):
        request = self.context.get('request')
        if request and hasattr(request.user, 'client_profile'):
            return obj.inscriptions.filter(client=request.user.client_profile).exists()
        return False

    def get_mon_statut(self, obj):
        request = self.context.get('request')
        if request and hasattr(request.user, 'client_profile'):
            ins = obj.inscriptions.filter(client=request.user.client_profile).first()
            return ins.statut if ins else None
        return None

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def validate(self, data):
        request = self.context.get('request')
        coach = None

        if request and hasattr(request.user, 'coach_profile'):
            coach = request.user.coach_profile
        elif 'programme' in data and data['programme']:
            coach = data['programme'].coach

        if not coach:
            return data

        nouveau_jour = data.get('jour_prevu')
        nouvelle_heure_debut = data.get('heure_debut')
        nouvelle_heure_fin = data.get('heure_fin')

        if self.instance:
            nouveau_jour = nouveau_jour or self.instance.jour_prevu
            nouvelle_heure_debut = nouvelle_heure_debut or self.instance.heure_debut
            nouvelle_heure_fin = nouvelle_heure_fin or self.instance.heure_fin

        if nouveau_jour:
            maintenant = timezone.localtime()
            date_aujourdhui = maintenant.date()
            heure_actuelle = maintenant.time()

            if nouveau_jour < date_aujourdhui:
                raise serializers.ValidationError({
                    "jour_prevu": "Vous ne pouvez pas planifier une séance à une date passée."
                })

            if nouveau_jour == date_aujourdhui and nouvelle_heure_debut:
                if nouvelle_heure_debut < heure_actuelle:
                    raise serializers.ValidationError({
                        "heure_debut": "L'heure de début ne peut pas être inférieure à l'heure actuelle."
                    })

        if not (nouveau_jour and nouvelle_heure_debut and nouvelle_heure_fin):
            return data

        from .models import Seance, Indisponibilite

        seances_chevauchees = Seance.objects.filter(
            coach=coach,
            jour_prevu=nouveau_jour,
            heure_debut__lt=nouvelle_heure_fin,
            heure_fin__gt=nouvelle_heure_debut
        )

        if self.instance:
            seances_chevauchees = seances_chevauchees.exclude(id=self.instance.id)

        if seances_chevauchees.exists():
            raise serializers.ValidationError({
                "horaire_conflit": "Vous avez déjà une autre séance prévue sur ce créneau."
            })

        indispos_chevauchees = Indisponibilite.objects.filter(
            coach=coach,
            jour_prevu=nouveau_jour,
            heure_debut__lt=nouvelle_heure_fin,
            heure_fin__gt=nouvelle_heure_debut
        )

        if indispos_chevauchees.exists():
            raise serializers.ValidationError({
                "horaire_conflit": "Vous avez déclaré une indisponibilité ou un congé sur ce créneau."
            })

        return data

class ProgrammeSerializer(serializers.ModelSerializer):
    nb_seances = serializers.SerializerMethodField()
    seances = serializers.SerializerMethodField()

    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']

    def get_nb_seances(self, obj):
        from .models import Seance
        return Seance.objects.filter(programme=obj).count()

    def get_seances(self, obj):
        from .models import Seance
        seances = Seance.objects.filter(programme=obj)
        return SeanceSerializer(seances, many=True).data

class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = '__all__'
        read_only_fields = ['id', 'client', 'date_enregistrement']

class IndisponibiliteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indisponibilite
        fields = '__all__'
        read_only_fields = ['coach']

# --- NOTIFICATIONS ---
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['id', 'coach', 'date_creation']

class NotificationAthleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationAthlete
        fields = '__all__'
        read_only_fields = ['id', 'client', 'date_creation']

class SalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salle
        fields = '__all__'

class AvisSerializer(serializers.ModelSerializer):
    client_name = serializers.ReadOnlyField(source='client.user.get_full_name')

    class Meta:
        model = Avis
        fields = '__all__'

class ProspectCoachListSerializer(serializers.ModelSerializer):
    nom = serializers.SerializerMethodField()
    email = serializers.ReadOnlyField(source='user.email')
    note_moyenne = serializers.SerializerMethodField()
    nombre_avis = serializers.SerializerMethodField()
    programmes_gratuits = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Coach
        fields = [
            'id',
            'nom',
            'email',
            'telephone',
            'ville',
            'distance_km',
            'specialite',
            'specialites_tags',
            'offres_tarifs',
            'note_moyenne',
            'nombre_avis',
            'programmes_gratuits',
        ]

    def get_nom(self, obj):
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full_name if full_name else obj.user.username

    def get_note_moyenne(self, obj):
        avis = obj.avis.all()
        if not avis.exists():
            return 0
        return round(sum(a.note for a in avis) / avis.count(), 1)

    def get_nombre_avis(self, obj):
        return obj.avis.count()

    def get_programmes_gratuits(self, obj):
        programmes = obj.programmes_crees.all()[:3]
        return [
            {
                "id": p.id,
                "titre": p.titre,
                "description": p.description,
            }
            for p in programmes
        ]
    def get_distance_km(self, obj):
        distance_map = self.context.get("distance_map", {})
        d = distance_map.get(obj.id)

        if d is None:
            return None
        return round(d, 2)


class ProspectCoachDetailSerializer(ProspectCoachListSerializer):
    avis = AvisSerializer(many=True, read_only=True)

    class Meta(ProspectCoachListSerializer.Meta):
        fields = ProspectCoachListSerializer.Meta.fields + ['avis']

class DevisSerializer(serializers.ModelSerializer):
    coach_nom = serializers.SerializerMethodField()

    class Meta:
        model = Devis
        fields = '__all__'

    def get_coach_nom(self, obj):
        full_name = f"{obj.coach.user.first_name} {obj.coach.user.last_name}".strip()
        return full_name or obj.coach.user.username
    
    from .models import ActiviteExterne

# --- NOUVEAU : Serializer pour les activités Strava/Garmin ---
class ActiviteExterneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActiviteExterne
        fields = '__all__'

# --- NOUVEAU : Serializer pour la Boutique ---
class ProduitSerializer(serializers.ModelSerializer):
    # Permet d'afficher le nom de la catégorie au lieu de l'ID
    categorie_nom = serializers.ReadOnlyField(source='categorie.nom')
    # Permet d'afficher le nom du coach qui vend le produit
    coach_nom = serializers.ReadOnlyField(source='coach.user.username')

    class Meta:
        model = Produit
        fields = '__all__'
        # Le coach est défini automatiquement par la vue, pas par l'utilisateur
        read_only_fields = ['coach']

class CategorieProduitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieProduit
        fields = '__all__'