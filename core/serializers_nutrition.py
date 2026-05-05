from rest_framework import serializers
from .models import Recette, PlanNutritionnel

class RecetteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recette
        fields = '__all__'
        read_only_fields = ['coach'] # Le coach sera assigné automatiquement par la vue

class PlanNutritionnelSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanNutritionnel
        fields = '__all__'
        read_only_fields = ['coach', 'produit'] # Le coach sera assigné automatiquement