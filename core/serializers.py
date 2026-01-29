from rest_framework import serializers
from .models import Client, Coach

# Serializer pour l'Annuaire (Issue #5)
class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'
        # Le coach est rempli par le serveur, pas par le formulaire
        read_only_fields = ['coach']

# Serializer pour l'Onboarding du Coach (Issue #F2 Front)
class CoachSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coach
        # Tous les champs DOIVENT être indentés sous 'class Meta'
        fields = ['specialites_tags', 'offres_tarifs', 'telephone', 'specialite']