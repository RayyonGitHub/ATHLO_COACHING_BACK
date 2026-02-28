from rest_framework import serializers
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice

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
        fields = ['specialites_tags', 'offres_tarifs', 'telephone', 'specialite']

# --- NOUVEAUX SERIALIZERS (Issue #9 et #10) ---

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
    volume_total = serializers.ReadOnlyField() # On expose le calcul automatique

    class Meta:
        model = Seance
        fields = [
            'id', 'programme', 'titre', 'ordre', 'jour_prevu', 
            'est_completee', 'commentaire_coach', 'ressenti_client', 
            'notes_client', 'exercices_details', 'volume_total'
        ]

class ProgrammeSerializer(serializers.ModelSerializer):
    # On imbrique les séances dans le programme
    seances = SeanceSerializer(many=True, read_only=True)
    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']