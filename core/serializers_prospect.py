from rest_framework import serializers
from .models import Coach, Client, Programme, Devis

class PublicCoachSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True)
    full_name = serializers.CharField()
    ville = serializers.CharField(allow_blank=True)
    specialites = serializers.ListField(child=serializers.CharField(), default=list)
    note = serializers.FloatField()
    avis = serializers.IntegerField()
    tarifs = serializers.DictField()
    programmes_gratuits = serializers.ListField(child=serializers.DictField(), default=list)
    image = serializers.CharField(allow_blank=True, allow_null=True, required=False)


class ProspectActivateAthleteSerializer(serializers.Serializer):
    checkout_token = serializers.CharField()

    prenom = serializers.CharField(max_length=100)
    nom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(max_length=20, allow_blank=True, required=False)

    age = serializers.IntegerField(required=False, allow_null=True)
    taille = serializers.IntegerField(required=False, allow_null=True)
    poids = serializers.FloatField(required=False, allow_null=True)

    genre = serializers.ChoiceField(choices=[('M', 'Homme'), ('F', 'Femme'), ('O', 'Autre')], default='M')
    niveau_activite = serializers.ChoiceField(
        choices=[
            ('1.2', 'Sédentaire'),
            ('1.375', 'Légèrement actif'),
            ('1.55', 'Modérément actif'),
            ('1.725', 'Très actif'),
            ('1.9', 'Extrêmement actif'),
        ],
        default='1.55'
    )

    poids_cible = serializers.FloatField(required=False, allow_null=True)
    type_entrainement = serializers.CharField(required=False, allow_blank=True, default='Musculation')
    objectifs_sportifs = serializers.CharField(required=False, allow_blank=True, default='')
    pathologies_blessures = serializers.CharField(required=False, allow_blank=True, default='')
    consentement_rgpd = serializers.BooleanField(required=False, default=True)


class ProspectDevisCreateSerializer(serializers.Serializer):
    coach_id = serializers.IntegerField()

    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    telephone = serializers.CharField(max_length=20, allow_blank=True, required=False)

    age = serializers.IntegerField(required=False, allow_null=True)
    taille = serializers.IntegerField(required=False, allow_null=True)
    poids = serializers.FloatField(required=False, allow_null=True)

    niveauActivite = serializers.CharField(required=False, allow_blank=True)
    typeEntrainement = serializers.CharField(required=False, allow_blank=True)
    objectifSportif = serializers.CharField(required=False, allow_blank=True)
    budget = serializers.CharField(required=False, allow_blank=True)
    pathologiesBlessures = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)

