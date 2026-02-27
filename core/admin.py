from django.contrib import admin
from .models import Coach, Client,Exercice
# Register your models here.
admin.site.register(Coach)
admin.site.register(Client)
admin.site.register(Exercice)