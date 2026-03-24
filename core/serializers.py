from rest_framework import serializers
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
    nombre_inscrits = serializers.SerializerMethodField()
    places_restantes = serializers.SerializerMethodField()
    exercices = serializers.SerializerMethodField()
    exercices_details = serializers.SerializerMethodField()

    class Meta:
        model = Seance
        fields = '__all__'
        read_only_fields = ['coach']

    # --- TES FONCTIONS EXISTANTES ---
    def get_nombre_inscrits(self, obj):
        # Utilisation de .all() pour éviter les erreurs si la relation n'est pas instanciée
        if not hasattr(obj, 'inscriptions'): return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()

    def get_places_restantes(self, obj):
        if not obj.capacite_max: return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)

    # --- LES NOUVELLES FONCTIONS POUR AFFICHER LES EXERCICES ---
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

    # Double sécurité : certains Frontends cherchent "exercices", d'autres "exercices_details"
    def get_exercices_details(self, obj):
        return self.get_exercices(obj)

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