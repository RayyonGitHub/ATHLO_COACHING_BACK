from rest_framework import serializers
import datetime
from django.utils import timezone
from .models import (
    Client, Coach, Exercice, Programme, Seance, 
    SeanceExercice, Performance, Indisponibilite, 
    Inscription, Notification, NotificationAthlete, Salle, Avis
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
    client_name = serializers.ReadOnlyField(source='client.user.get_full_name')
    client_id = serializers.ReadOnlyField(source='client.id')
    class Meta:
        model = Inscription
        fields = ['id', 'client_id', 'client_name', 'statut', 'date_inscription']

# Dans serializers.py
class SeanceSerializer(serializers.ModelSerializer):
    # 1. IL FAUT DÉCLARER LES CHAMPS ICI POUR QUE LE FRONTEND LES REÇOIVE

    exercices = serializers.SerializerMethodField()
    exercices_details = serializers.SerializerMethodField()
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()  
    # --- NOUVEAUX CHAMPS POUR LES PARTICIPANTS ---
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
        # Utilisation de .all() pour éviter les erreurs si la relation n'est pas instanciée
        if not hasattr(obj, 'inscriptions'): return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()

    def get_places_restantes(self, obj):
        if not obj.capacite_max: return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)

    def get_exercices(self, obj):
        from .models import SeanceExercice
        # On va chercher tous les exercices liés à CETTE séance spécifique
        exos = SeanceExercice.objects.filter(seance=obj).order_by('ordre')
         # On fabrique une liste propre pour que React puisse tout lire facilement
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
        # Mise à jour simple : appliquer tous les champs validés
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    # Double sécurité : certains Frontends cherchent "exercices", d'autres "exercices_details"
    def get_exercices_details(self, obj):
        return self.get_exercices(obj)
    def validate(self, data):
        # 1. On récupère les infos de la requête
        request = self.context.get('request')
        coach = None

        # On identifie le coach (soit celui connecté, soit celui assigné au programme)
        if request and hasattr(request.user, 'coach_profile'):
            coach = request.user.coach_profile
        elif 'programme' in data and data['programme']:
            coach = data['programme'].coach

        if not coach:
            return data # Si pas de coach, on laisse passer (cas rare)

        # 2. On récupère les nouveaux horaires
        nouveau_jour = data.get('jour_prevu')
        nouvelle_heure_debut = data.get('heure_debut')
        nouvelle_heure_fin = data.get('heure_fin')

        # Si l'utilisateur modifie une séance existante, il n'envoie pas forcément toutes les dates.
        # On complète avec les anciennes données de l'instance si nécessaire.
        if self.instance:
            nouveau_jour = nouveau_jour or self.instance.jour_prevu
            nouvelle_heure_debut = nouvelle_heure_debut or self.instance.heure_debut
            nouvelle_heure_fin = nouvelle_heure_fin or self.instance.heure_fin
        if nouveau_jour:
            from django.utils import timezone
            
            # timezone.localtime() force la récupération de l'heure selon le TIME_ZONE des settings (Paris)
            maintenant = timezone.localtime() 
            date_aujourdhui = maintenant.date()
            heure_actuelle = maintenant.time()

            if nouveau_jour < date_aujourdhui:
                raise serializers.ValidationError({
                    "jour_prevu": "Vous ne pouvez pas planifier une séance à une date passée."
                })
            
            # Si c'est aujourd'hui, on vérifie l'heure Bouthayna
            if nouveau_jour == date_aujourdhui and nouvelle_heure_debut:
                if nouvelle_heure_debut < heure_actuelle:
                    raise serializers.ValidationError({
                        "heure_debut": "L'heure de début ne peut pas être inférieure à l'heure actuelle."
                    })
        # Si la séance n'a pas de date ou d'heure précise, on ne bloque pas
        if not (nouveau_jour and nouvelle_heure_debut and nouvelle_heure_fin):
            return data

        # 3. VERIFICATION N°1 : Les autres séances du coach
        from .models import Seance, Indisponibilite # Import local pour éviter les boucles
        seances_chevauchees = Seance.objects.filter(
            coach=coach,
            jour_prevu=nouveau_jour,
            heure_debut__lt=nouvelle_heure_fin,
            heure_fin__gt=nouvelle_heure_debut
        )
        
        # Si on est en train de modifier une séance, on exclut la séance elle-même !
        if self.instance:
            seances_chevauchees = seances_chevauchees.exclude(id=self.instance.id)

        if seances_chevauchees.exists():
            raise serializers.ValidationError({
                "horaire_conflit": "Vous avez déjà une autre séance prévue sur ce créneau."
            })

        # 4. VERIFICATION N°2 : Les congés et indisponibilités du coach
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
    # On crée deux champs personnalisés "sur mesure"
    nb_seances = serializers.SerializerMethodField()
    seances = serializers.SerializerMethodField()

    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']

    # 1. On force le calcul exact du nombre de séances pour ce programme
    def get_nb_seances(self, obj):
        from .models import Seance
        return Seance.objects.filter(programme=obj).count()

    # 2. On force la récupération de toutes les données des séances
    def get_seances(self, obj):
        from .models import Seance
        seances = Seance.objects.filter(programme=obj)
        # On utilise le SeanceSerializer pour formater la réponse
        return SeanceSerializer(seances, many=True).data

class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = '__all__'
        # 🎯 ON MET 'client' ET NON 'athlete'
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

# 🔔 AJOUT POUR TON TRAVAIL (Indispensable pour views.py)
class NotificationAthleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationAthlete
        fields = '__all__'
        # 🎯 ON REMPLACE 'athlete' PAR 'client' :
        read_only_fields = ['id', 'client', 'date_creation']

# 🏢 AJOUT POUR TES COLLÈGUES (Indispensable pour views.py)
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