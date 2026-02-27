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
    # On imbrique les exercices dans la séance
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    class Meta:
        model = Seance
        fields = '__all__'

class ProgrammeSerializer(serializers.ModelSerializer):
    # On imbrique les séances dans le programme
    seances = SeanceSerializer(many=True, read_only=True)
    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']