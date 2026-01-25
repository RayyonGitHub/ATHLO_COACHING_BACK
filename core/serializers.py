# Ce fichier sert à transformer les données en format JSON pour que React puisse les lire
from rest_framework import serializers
from .models import Client
class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model=Client
        fields= '__all__' #Pour avoir tout les champs