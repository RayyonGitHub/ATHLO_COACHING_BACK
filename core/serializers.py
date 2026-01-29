from rest_framework import serializers
from .models import Client

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'
        # Coach non requis dans le Front attribution du coach connecté par défaut
        read_only_fields = ['coach']