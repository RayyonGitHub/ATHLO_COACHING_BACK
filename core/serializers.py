from rest_framework import serializers
# Ajout de Performance dans les imports
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite, Inscription

# Serializer pour l'Annuaire
class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['coach', 'user']

# Serializer pour l'Onboarding du Coach
class CoachSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coach
        fields = ['id', 'specialites_tags', 'offres_tarifs', 'telephone', 'specialite']
# --- SERIALIZERS SPORTIFS ---

class ExerciceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercice
        fields = '__all__'

class SeanceExerciceSerializer(serializers.ModelSerializer):
    # On imbrique l'exercice pour avoir son nom et sa vidéo directement
    exercice_details = ExerciceSerializer(source='exercice', read_only=True)
    class Meta:
        model = SeanceExercice
        fields = '__all__'

class InscriptionDetailsSerializer(serializers.ModelSerializer):
    # On récupère le nom du client depuis le profil utilisateur
    client_name = serializers.ReadOnlyField(source='client.user.get_full_name')
    client_id = serializers.ReadOnlyField(source='client.id')

    class Meta:
        model = Inscription
        fields = ['id', 'client_id', 'client_name', 'statut', 'date_inscription']

class SeanceSerializer(serializers.ModelSerializer):
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()
    
    # --- NOUVEAUX CHAMPS POUR LES PARTICIPANTS ---
    participants = InscriptionDetailsSerializer(source='inscriptions', many=True, read_only=True)
    
    nombre_inscrits = serializers.SerializerMethodField()
    places_restantes = serializers.SerializerMethodField()

    class Meta:
        model = Seance
        fields = [
            'id', 'coach', 'programme', 'titre', 'ordre', 'jour_prevu', 
            'heure_debut', 'heure_fin', 'est_collective', 'capacite_max',
            'est_completee', 'commentaire_coach', 'ressenti_client', 
            'notes_client', 'exercices_details', 'volume_total',
            'participants', 'nombre_inscrits', 'places_restantes'
        ]
        read_only_fields = ['coach']

    def validate_capacite_max(self, value):
        if value is None:
            return 1
        try:
            return int(value)
        except (ValueError, TypeError):
            return 1

    def get_nombre_inscrits(self, obj):
        # On vérifie que 'inscriptions' existe pour éviter les plantages
        if not hasattr(obj, 'inscriptions'):
            return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()

    def get_places_restantes(self, obj):
        if not obj.capacite_max:
            return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)
    def update(self, instance, validated_data):
        # On vérifie si on est en train de décocher la case 'est_completee'
        nouvelle_completude = validated_data.get('est_completee', instance.est_completee)
        
        if instance.est_completee == True and nouvelle_completude == False:
            # Le coach a annulé la fin de séance ! 
            # On remet tous les PRESENT et ABSENT en CONFIRME
            instance.inscriptions.filter(statut__in=['PRESENT', 'ABSENT']).update(statut='CONFIRME')
            
        return super().update(instance, validated_data)

class ProgrammeSerializer(serializers.ModelSerializer):
    # On imbrique les séances dans le programme
    seances = SeanceSerializer(many=True, read_only=True)
    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']

# --- NOUVEAU SERIALIZER : ISSUE #14 ---
class PerformanceSerializer(serializers.ModelSerializer):
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

class IndisponibiliteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indisponibilite
        fields = '__all__'
        read_only_fields = ['coach']