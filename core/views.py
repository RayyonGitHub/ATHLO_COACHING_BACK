#from django.shortcuts import render
from rest_framework import viewsets
from .models import Client
from .serializers import ClientSerializer
# ModelViewSet for automatic CRUD methods
class ClientViewSet(viewsets.ModelViewSet):
    queryset=Client.objects.all()
    serializer_class=ClientSerializer