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

class SeanceSerializer(serializers.ModelSerializer):
    exercices_details = SeanceExerciceSerializer(many=True, read_only=True)
    volume_total = serializers.ReadOnlyField()
    participants = InscriptionDetailsSerializer(source='inscriptions', many=True, read_only=True)
    nombre_inscrits = serializers.SerializerMethodField()
    places_restantes = serializers.SerializerMethodField()
    class Meta:
        model = Seance
        fields = '__all__'
        read_only_fields = ['coach']
    def get_nombre_inscrits(self, obj):
        if not hasattr(obj, 'inscriptions'): return 0
        return obj.inscriptions.filter(statut='CONFIRME').count()
    def get_places_restantes(self, obj):
        if not obj.capacite_max: return 0
        return obj.capacite_max - self.get_nombre_inscrits(obj)

class ProgrammeSerializer(serializers.ModelSerializer):
    seances = SeanceSerializer(many=True, read_only=True)
    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['coach']

class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = '__all__'
        read_only_fields = ['id', 'date_enregistrement']

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
        read_only_fields = ['id', 'date_creation']

# 🔔 AJOUT POUR TON TRAVAIL (Indispensable pour views.py)
class NotificationAthleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationAthlete
        fields = '__all__'

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