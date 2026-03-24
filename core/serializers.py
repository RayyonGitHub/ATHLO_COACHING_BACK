from rest_framework import serializers
from .models import (
    Client, Coach, Exercice, Programme, Seance, 
    SeanceExercice, Performance, Indisponibilite, 
    Inscription, Notification
)

# --- 1. PROFILS ---

class ClientSerializer(serializers.ModelSerializer):
    """
    Serializer complet pour le profil de l'athlète.
    Inclut les nouveaux champs : genre, niveau_activite, poids_cible, etc.
    """
    class Meta:
        model = Client
        fields = '__all__'
        # Sécurité : on empêche l'athlète de changer son coach ou son compte user via l'API profil
        read_only_fields = ['coach', 'user', 'date_creation']

class CoachSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coach
        fields = ['id', 'specialites_tags', 'offres_tarifs', 'telephone', 'specialite', 'ville']

# --- 2. EXERCICES ET PERFORMANCES ---

class ExerciceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercice
        fields = '__all__'

class PerformanceSerializer(serializers.ModelSerializer):
    """ Utilise pour l'enregistrement des séries et du poids pendant la séance """
    class Meta:
        model = Performance
        fields = [
            'id', 
            'seance_exercice', 
            'series_realisees', 
            'reps_realisees', 
            'poids_utilise', 
            'notes_athlete', 
            'date_enregistrement'
        ]
        read_only_fields = ['id', 'date_enregistrement']

# --- 3. SÉANCES ET INSCRIPTIONS ---

class SeanceExerciceSerializer(serializers.ModelSerializer):
    # On imbrique l'exercice pour avoir son nom et sa vidéo directement
    exercice_details = ExerciceSerializer(source='exercice', read_only=True)
    
    class Meta:
        model = SeanceExercice
        fields = '__all__'

class InscriptionDetailsSerializer(serializers.ModelSerializer):
    # Utile pour afficher la liste des participants d'une séance au coach
    client_name = serializers.ReadOnlyField(source='client.user.get_full_name')
    client_id = serializers.ReadOnlyField(source='client.id')

    class Meta:
        model = Inscription
        fields = ['id', 'client_id', 'client_name', 'statut', 'date_inscription']

class SeanceSerializer(serializers.ModelSerializer):
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()
    
    # Détails des participants pour le coach
    participants = InscriptionDetailsSerializer(source='inscriptions', many=True, read_only=True)
    
    nombre_inscrits = serializers.SerializerMethodField()
    places_restantes = serializers.SerializerMethodField()

    class Meta:
        model = Seance
        fields = '__all__'
        read_only_fields = ['coach']

    def validate_capacite_max(self, value):
        if value is None:
            return 1
        try:
            return int(value)
        except (ValueError, TypeError):
            return 1

    def get_nombre_inscrits(self, obj):
        if not hasattr(obj, 'inscriptions'):
            return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()

    def get_places_restantes(self, obj):
        if not obj.capacite_max:
            return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)

    def update(self, instance, validated_data):
        # Logique spéciale : si on décoche 'est_completee', on remet les inscrits en 'CONFIRME'
        nouvelle_completude = validated_data.get('est_completee', instance.est_completee)
        
        if instance.est_completee == True and nouvelle_completude == False:
            instance.inscriptions.filter(statut__in=['PRESENT', 'ABSENT']).update(statut='CONFIRME')
            
        return super().update(instance, validated_data)

# --- 4. PROGRAMMES ET CALENDRIER ---

class ProgrammeSerializer(serializers.ModelSerializer):
    # On imbrique les séances dans le programme
    seances = SeanceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']

class IndisponibiliteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indisponibilite
        fields = '__all__'
        read_only_fields = ['coach']

# --- 5. NOTIFICATIONS ---

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'message', 'type', 'est_lu', 'date_creation', 'seance']
        read_only_fields = ['id', 'date_creation']