from rest_framework import serializers
# Ajout de Performance dans les imports
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite

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

class SeanceSerializer(serializers.ModelSerializer):
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()

    class Meta:
        model = Seance
        fields = [
            'id', 'coach', 'programme', 'titre', 'ordre', 'jour_prevu', 
            'heure_debut', 'heure_fin', 'est_collective', 'capacite_max',
            'est_completee', 'commentaire_coach', 'ressenti_client', 
            'notes_client', 'exercices_details', 'volume_total'
        ]
        read_only_fields = ['coach'] # Sécurité : le coach est déduit automatiquement

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