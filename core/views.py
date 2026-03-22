from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
import datetime
from django.http import HttpResponse
from icalendar import Calendar, Event
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework import viewsets, status, generics 
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework.exceptions import PermissionDenied

# Ajout de Performance et PerformanceSerializer
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer, IndisponibiliteSerializer


# --- Vues Existantes ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def perform_create(self, serializer):
        try:
            coach_profile = self.request.user.coach_profile
            serializer.save(coach=coach_profile)
        except Coach.DoesNotExist:
            raise PermissionDenied("Vous n'avez pas de profil Coach associé.")

class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach)
        return Response(serializer.data)

    def patch(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        serializer = CoachSerializer(coach, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AthleteMeView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        client, created = Client.objects.get_or_create(
            user=request.user,
            defaults={
                'email': request.user.email,
                'nom': request.user.last_name,
                'prenom': request.user.first_name
            }
        )
        serializer = ClientSerializer(client, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)


# --- VUE DÉMO ---

class DemoStatsView(APIView):
    permission_classes = [AllowAny] 

    def get(self, request):
        data = {
            "total_exercices": Exercice.objects.count(),
            "total_coachs": Coach.objects.count(),
            "utilisateurs_actifs": User.objects.count(),
            "programmes_crees": Programme.objects.count(), 
            "message": "Ceci est une démo. Connectez-vous pour accéder à votre suivi personnalisé."
        }
        return Response(data)


# --- NOUVELLES VUES SPORTIVES ---

class ExerciceViewSet(viewsets.ModelViewSet):
    queryset = Exercice.objects.all()
    serializer_class = ExerciceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ['categorie']

class ProgrammeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgrammeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Programme.objects.filter(coach=user.coach_profile)
        elif hasattr(user, 'client_profile'):
            return Programme.objects.filter(athlete=user.client_profile)
        return Programme.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            raise PermissionDenied("Seuls les coachs peuvent créer un programme.")


# --- VUE POUR LE CRÉATEUR DE SÉANCE ---

class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            # On autorise les séances liées directement au coach OU via un programme
            return Seance.objects.filter(
                Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)
            ).distinct()
        elif hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    @transaction.atomic 
    def create(self, request, *args, **kwargs):
        data = request.data
        programme_id = data.get('programme_id')

        # --- CAS 1 : Création directe depuis l'Agenda (sans programme) ---
        if not programme_id:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save(coach=request.user.coach_profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # --- CAS 2 : Création depuis le créateur de Programme (Ton ancien code) ---
        titre = data.get('titre')
        exercices_data = data.get('exercices', [])

        if not titre:
            return Response({"error": "Le titre est requis."}, status=status.HTTP_400_BAD_REQUEST)

        programme = get_object_or_404(Programme, id=programme_id)

        if not hasattr(request.user, 'coach_profile') or programme.coach != request.user.coach_profile:
            raise PermissionDenied("Vous n'êtes pas autorisé à ajouter une séance à ce programme.")

        ordre_seance = Seance.objects.filter(programme=programme).count() + 1

        seance = Seance.objects.create(
            coach=request.user.coach_profile, # Ajouté ici par sécurité
            programme=programme,
            titre=titre,
            ordre=ordre_seance
        )

        for exo_data in exercices_data:
            exercice = get_object_or_404(Exercice, id=exo_data.get('exercice_id'))
            SeanceExercice.objects.create(
                seance=seance,
                exercice=exercice,
                series=exo_data.get('series', 3),
                repetitions=exo_data.get('repetitions', '10'),
                poids=exo_data.get('poids', 'Poids du corps'),
                repos=exo_data.get('repos', '60s'),
                ordre=exo_data.get('ordre', 1)
            )

        serializer = self.get_serializer(seance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# --- VUES ANALYTICS ET DASHBOARD ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
            
        client = user.client_profile

        prochaine_seance = Seance.objects.filter(
            programme__athlete=client,
            est_completee=False
        ).order_by('jour_prevu', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            nb_exos = prochaine_seance.exercices_details.count()
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "programme_titre": prochaine_seance.programme.titre,
                "duree_estimee": nb_exos * 10 if nb_exos > 0 else 45,
                "calories_estimees": nb_exos * 80 if nb_exos > 0 else 450,
            }

        data = {
            "prenom": client.prenom or user.username,
            "prochaine_seance": seance_data,
            "stats_sante": {
                "completion_jour": 75,
                "calories": 1840,
                "calories_max": 2400,
                "recuperation": 94,
            }
        }
        return Response(data)

    
class CoachAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Accès réservé aux coachs."}, status=403)
        
        coach = request.user.coach_profile
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6) 

        total_athletes = coach.clients.count()

        seances_7_jours = Seance.objects.filter(
            programme__coach=coach,
            jour_prevu__range=[seven_days_ago, today]
        )

        total_seances = seances_7_jours.count()
        seances_completees = seances_7_jours.filter(est_completee=True).count()

        completion_rate = 0
        if total_seances > 0:
            completion_rate = round((seances_completees / total_seances) * 100, 1)
        
        total_volume = seances_completees * 450
        
        chart_data = []
        for i in range(7):
            date_target = seven_days_ago + timedelta(days=i)
            count_day = seances_7_jours.filter(
                jour_prevu=date_target, 
                est_completee=True
            ).count()
            
            chart_data.append({
                "day": date_target.strftime('%a'),
                "sessions": count_day
            })

        return Response({
            "total_athletes": total_athletes,
            "completion_rate": completion_rate,
            "total_volume": total_volume,  
            "chart_data": chart_data,
            "period": "7 derniers jours"
        })

# --- NOUVELLE VUE : ISSUE #14 (Enregistrement de Performance) ---

class PerformanceCreateView(generics.CreateAPIView):
    serializer_class = PerformanceSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # On lie automatiquement la performance au client connecté
        if hasattr(self.request.user, 'client_profile'):
            serializer.save(client=self.request.user.client_profile)
        else:
            raise PermissionDenied("Seul un athlète peut enregistrer une performance.")

class CoachCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, coach_id):
        coach = get_object_or_404(Coach, id=coach_id)
        
        # 1. Traitement des Séances
        seances = Seance.objects.filter(
            coach=coach
        ).prefetch_related('inscriptions__client')
        
        data = []
        for s in seances:
            inscriptions = s.inscriptions.filter(statut='CONFIRME')
            nb_inscrits = inscriptions.count()

            # CAS 1 : Séance Collective (Groupe)
            if s.est_collective:
                noms_liste = [f"{ins.client.prenom} {ins.client.nom.upper()}" for ins in inscriptions]
                client_display = ", ".join(noms_liste) if noms_liste else "Aucun inscrit"
                capacity_info = f"{nb_inscrits}/{s.capacite_max}"
            
            # CAS 2 : Séance Individuelle
            else:
                athlete = s.programme.athlete if s.programme else None
                
                if athlete:
                    # Cas classique : l'athlète est déjà assigné au programme
                    client_display = f"{athlete.prenom} {athlete.nom.upper()}"
                    capacity_info = "1/1"
                elif nb_inscrits > 0:
                    # Cas où on a utilisé la table Inscription pour une séance individuelle
                    first_ins = inscriptions.first()
                    client_display = f"{first_ins.client.prenom} {first_ins.client.nom.upper()}"
                    capacity_info = "1/1"
                else:
                    # Cas "ana ana" : pas d'athlète sur le programme et pas d'inscription
                    client_display = "En attente d'athlète"
                    capacity_info = "0/1"

            data.append({
                "id": f"seance_{s.id}",       # ID unique pour React
                "db_id": s.id,                # ID en DB si besoin d'éditer
                "title": s.titre,
                "start": f"{s.jour_prevu}T{s.heure_debut}" if s.heure_debut else str(s.jour_prevu),
                "end": f"{s.jour_prevu}T{s.heure_fin}" if s.heure_fin else None,
                "is_collective": s.est_collective,
                "type": "collective" if s.est_collective else "individuelle",
                "capacity_label": capacity_info,
                "client_name": client_display,
                "completed": s.est_completee
            })
            
        # 2. Traitement des Indisponibilités
        indispos = Indisponibilite.objects.filter(coach=coach)
        for ind in indispos:
            data.append({
                "id": f"indispo_{ind.id}",
                "db_id": ind.id,
                "title": ind.titre,
                # 👇 LES DEUX LIGNES QUI CHANGENT 👇
                "start": f"{ind.jour_prevu}T{ind.heure_debut}",
                "end": f"{ind.jour_prevu}T{ind.heure_fin}",
                # 👆 ---------------------------- 👆
                "is_collective": False,
                "type": "conge" if ind.est_conge else "indisponibilite",
                "capacity_label": "",
                "client_name": "",
                "completed": False
            })
        
        return Response(data)
    
class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Un coach ne voit/gère que ses propres indisponibilités
        if hasattr(self.request.user, 'coach_profile'):
            return Indisponibilite.objects.filter(coach=self.request.user.coach_profile)
        return Indisponibilite.objects.none()

    def perform_create(self, serializer):
        # On assigne automatiquement le coach connecté
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            raise PermissionDenied("Seuls les coachs peuvent créer des indisponibilités.")
        

@api_view(['GET'])
@permission_classes([AllowAny]) # Google Calendar n'a pas de token de connexion, il faut que l'URL soit lisible
def export_coach_calendar(request, coach_id):
    coach = get_object_or_404(Coach, id=coach_id)
    cal = Calendar()
    
    # Méta-données du calendrier
    cal.add('prodid', '-//Agenda Athlo Coach//athlo.com//')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', f'Agenda Athlo - {coach.user.first_name}') # Nom du calendrier dans Google

    # 1. On injecte toutes les Séances
    seances = Seance.objects.filter(coach=coach)
    for seance in seances:
        event = Event()
        event.add('summary', seance.titre if seance.titre else 'Séance de coaching')
        
        # On fusionne le jour et l'heure pour créer un vrai DateTime
        dt_start = datetime.datetime.combine(seance.jour_prevu, seance.heure_debut)
        dt_end = datetime.datetime.combine(seance.jour_prevu, seance.heure_fin)
        
        event.add('dtstart', dt_start)
        event.add('dtend', dt_end)
        event.add('description', 'Séance Collective' if seance.est_collective else 'Séance Individuelle')
        
        cal.add_component(event)

    # 2. On injecte toutes les Indisponibilités
    indispos = Indisponibilite.objects.filter(coach=coach)
    for indispo in indispos:
        event = Event()
        event.add('summary', indispo.titre if indispo.titre else 'Indisponible')
        
        dt_start = datetime.datetime.combine(indispo.jour_prevu, indispo.heure_debut)
        dt_end = datetime.datetime.combine(indispo.jour_prevu, indispo.heure_fin)
        
        event.add('dtstart', dt_start)
        event.add('dtend', dt_end)
        event.add('description', 'Congé' if indispo.est_conge else 'Indisponibilité')
        
        cal.add_component(event)

    # On renvoie le tout sous forme de fichier téléchargeable (.ics)
    response = HttpResponse(cal.to_ical(), content_type="text/calendar")
    response['Content-Disposition'] = f'attachment; filename="athlo_agenda_{coach_id}.ics"'
    
    return response