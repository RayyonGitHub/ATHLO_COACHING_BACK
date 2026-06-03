from rest_framework import serializers
from .models import Recette, PlanNutritionnel

class RecetteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recette
        fields = '__all__'
        read_only_fields = ['coach']

class PlanNutritionnelSerializer(serializers.ModelSerializer):
    recettes_details = RecetteSerializer(source='recettes', many=True, read_only=True)
    total_calories = serializers.SerializerMethodField()
    total_proteines = serializers.SerializerMethodField()
    total_glucides = serializers.SerializerMethodField()
    total_lipides = serializers.SerializerMethodField()

    class Meta:
        model = PlanNutritionnel
        fields = '__all__'
        read_only_fields = ['coach', 'produit']

    def get_total_calories(self, obj):
        return sum(r.calories or 0 for r in obj.recettes.all())

    def get_total_proteines(self, obj):
        return sum(r.proteines or 0 for r in obj.recettes.all())

    def get_total_glucides(self, obj):
        return sum(r.glucides or 0 for r in obj.recettes.all())

    def get_total_lipides(self, obj):
        return sum(r.lipides or 0 for r in obj.recettes.all())
