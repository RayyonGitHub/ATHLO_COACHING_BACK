import random # <-- NOUVEAU : Import pour le Mock intelligent
import datetime
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q, Sum, F, ExpressionWrapper, FloatField
from django.db.models.functions import TruncDate
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from icalendar import Calendar, Event
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.core.mail import send_mail

from rest_framework import viewsets, status, generics
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite, Inscription, Notification
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer, IndisponibiliteSerializer, NotificationSerializer

# --- Vues Profils ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def generate_password(self, length=10):
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def perform_create(self, serializer):
        coach_profile = self.request.user.coach_profile
        email = serializer.validated_data.get('email')

        existing_user = User.objects.filter(email=email).first()
        existing_client = Client.objects.filter(email=email).first()

        if existing_user and existing_client:
            client = existing_client
            client.coach = coach_profile
            client.nom = serializer.validated_data.get('nom')
            client.prenom = serializer.validated_data.get('prenom')
            client.save()
            return 
        elif existing_user:
            raise ValidationError("Un utilisateur avec cet email existe déjà.")

        temp_password = self.generate_password()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=temp_password,
            first_name=serializer.validated_data.get('prenom'),
            last_name=serializer.validated_data.get('nom')
        )

        serializer.save(coach=coach_profile, user=user)

        send_mail(
            subject="Vos identifiants de connexion",
            message=f"Bonjour {serializer.validated_data.get('prenom')},\n\nVotre compte coach a été créé.\nEmail: {email}\nMot de passe: {temp_password}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user:
            instance.user.delete()
        instance.delete()
        return Response(status=204)

class CoachMeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        coach, created = Coach.objects.get_or_create(user=request.user)
        return Response(CoachSerializer(coach).data)

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
            defaults={'email': request.user.email, 'nom': request.user.last_name, 'prenom': request.user.first_name}
        )
        serializer = ClientSerializer(client, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# --- VUES SPORTIVES ---

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

class SeanceViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'coach_profile'):
            return Seance.objects.filter(Q(coach=user.coach_profile) | Q(programme__coach=user.coach_profile)).distinct()
        elif hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    @transaction.atomic 
    def create(self, request, *args, **kwargs):
        data = request.data
        coach_profile = request.user.coach_profile
        
        # On récupère les infos de base
        titre = data.get('titre', 'Nouvelle séance')
        jour = data.get('jour_prevu')
        h_debut = data.get('heure_debut')
        h_fin = data.get('heure_fin')
        
        # Récupération du programme (facultatif)
        programme_id = data.get('programme_id')
        programme = None
        if programme_id:
            programme = get_object_or_404(Programme, id=programme_id)

        # CRÉATION DE LA SÉANCE
        seance = Seance.objects.create(
            coach=coach_profile,
            programme=programme,
            titre=titre,
            jour_prevu=jour,
            heure_debut=h_debut,
            heure_fin=h_fin,
            est_collective=data.get('est_collective', False),
            capacite_max=data.get('capacite_max', 1),
            est_completee=data.get('est_completee', False)
        )

        # Si tu as des exercices envoyés en même temps
        exercices_data = data.get('exercices', [])
        for exo_data in exercices_data:
            exercice = get_object_or_404(Exercice, id=exo_data.get('exercice_id'))
            SeanceExercice.objects.create(
                seance=seance,
                exercice=exercice,
                series=exo_data.get('series', 3),
                repetitions=exo_data.get('repetitions', '10'),
                poids=exo_data.get('poids', 'Poids du corps')
            )

        serializer = self.get_serializer(seance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Suppression des inscriptions sans signal
        instance.inscriptions.all().delete()
        
        # Notification de suppression de séance
        Notification.objects.create(
            coach=instance.coach,
            seance=None,
            type='ANNULATION',
            message=f"La séance '{instance.titre}' a été définitivement supprimée de l'agenda."
        )
        
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# --- ANALYTICS ET DASHBOARD ATHLÈTE ---

class AthleteDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"detail": "Vous n'êtes pas un athlète."}, status=403)
        client = request.user.client_profile

        prochaine_seance = Seance.objects.filter(
            Q(programme__athlete=client) | Q(inscriptions__client=client),
            est_completee=False
        ).order_by('jour_prevu', 'heure_debut', 'ordre').first()

        seance_data = None
        if prochaine_seance:
            nb_exos = prochaine_seance.exercices_details.count()
            seance_data = {
                "id": prochaine_seance.id,
                "titre": prochaine_seance.titre,
                "programme_titre": prochaine_seance.programme.titre if prochaine_seance.programme else "Séance indépendante",
                "duree_estimee": nb_exos * 10 or 45,
                "calories_estimees": nb_exos * 80 or 450,
            }

        programme_actuel = Programme.objects.filter(athlete=client).last()
        prog_data = None
        if programme_actuel:
            total = Seance.objects.filter(programme=programme_actuel).count()
            faits = Seance.objects.filter(programme=programme_actuel, est_completee=True).count()
            prog_data = {
                "titre": programme_actuel.titre, 
                "progression": int((faits/total)*100) if total > 0 else 0
            }

        # --- LE FAMEUX CALCUL DU BMR (CALORIES MAX) ---
        calories_max_objectif = 2400 
        if client.poids and client.taille and client.age:
            try:
                bmr = (10 * float(client.poids)) + (6.25 * float(client.taille)) - (5 * float(client.age)) + 5
                calories_max_objectif = int(bmr * 1.55)
            except (ValueError, TypeError):
                pass

        # --- CALCUL DES CALORIES BRÛLÉES AUJOURD'HUI ---
        today = timezone.now().date()
        performances_du_jour = Performance.objects.filter(
            client=client,
            date_enregistrement__date=today
        )
        total_series_jour = 0
        for perf in performances_du_jour:
            try:
                total_series_jour += int(perf.series_realisees)
            except (ValueError, TypeError):
                pass
        
        calories_brulees = total_series_jour * 15

        # --- COMPLÉTION DU CERCLE ---
        completion_jour = 0
        if calories_max_objectif > 0:
            completion_jour = min(int((calories_brulees / calories_max_objectif) * 100), 100)

        # --- LE MOCK INTELLIGENT (APIs Tierces) ---
        # On utilise une "graine" basée sur l'ID du client et la date du jour.
        # Résultat : Les données ont l'air aléatoires mais restent stables toute la journée !
        random.seed(client.id + today.toordinal())
        
        pas_jour = random.randint(4500, 12500)
        hydratation = round(random.uniform(0.8, 3.2), 1)
        sommeil_h = random.randint(5, 9)
        sommeil_m = random.randint(0, 59)
        fc_repos = random.randint(55, 80)
        recuperation = random.randint(60, 100)

        return Response({
            "prenom": client.prenom,
            "prochaine_seance": seance_data,
            "programme_actuel": prog_data,
            "stats_sante": {
                "completion_jour": completion_jour, 
                "calories": calories_brulees, 
                "calories_max": calories_max_objectif,
                "pas": pas_jour,                               # NOUVEAU
                "hydratation": hydratation,                    # NOUVEAU
                "sommeil": f"{sommeil_h}h {sommeil_m:02d}m",   # NOUVEAU
                "fc_repos": fc_repos,                          # NOUVEAU
                "recuperation": recuperation                   # NOUVEAU
            }
        })

class AthleteStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client_profile'):
            return Response({"detail": "Accès réservé aux athlètes."}, status=403)
        
        client = request.user.client_profile
        
        # 1. Calcul du Volume d'entraînement par jour (7 derniers jours)
        volume_data = Performance.objects.filter(client=client) \
            .annotate(day=TruncDate('date_enregistrement')) \
            .values('day') \
            .annotate(
                total_volume=Sum(
                    ExpressionWrapper(
                        F('poids_utilise') * F('reps_realisees') * F('series_realisees'),
                        output_field=FloatField()
                    )
                )
            ).order_by('day')[:7]

        # 2. Répartition par catégorie de muscle
        muscle_data = Performance.objects.filter(client=client) \
            .values(name=F('seance_exercice__exercice__categorie')) \
            .annotate(value=Sum('reps_realisees')) \
            .order_by('-value')

        # 3. Formatage pour le Frontend
        formatted_volume = [
            {
                "day": entry['day'].strftime('%a') if entry['day'] else "N/A",
                "volume": entry['total_volume'] or 0
            } for entry in volume_data
        ]

        return Response({
            "volume_history": formatted_volume,
            "muscle_distribution": list(muscle_data),
            "summary": {
                "total_sessions": Performance.objects.filter(client=client).values('seance_exercice__seance').distinct().count(),
                "total_reps": Performance.objects.filter(client=client).aggregate(Sum('reps_realisees'))['reps_realisees__sum'] or 0
            }
        })

# --- AUTRES VUES ---

class CoachAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Coach requis"}, status=403)
            
        coach = request.user.coach_profile
        
        # 1. Calcul du total des athlètes
        total_athletes = coach.clients.count()

        # 2. Vrai calcul de l'assiduité basé sur ton modèle Seance
        seances_totales = Seance.objects.filter(coach=coach).count()
        seances_faites = Seance.objects.filter(coach=coach, est_completee=True).count()
        completion_rate = int((seances_faites / seances_totales) * 100) if seances_totales > 0 else 0

        # 3. Vraies données pour le graphique : les séances complétées sur les 7 derniers jours
        aujourd_hui = timezone.now().date()
        il_y_a_7_jours = aujourd_hui - timedelta(days=6)
        
        # On regroupe les séances par jour
        seances_recentes = Seance.objects.filter(
            coach=coach, 
            jour_prevu__gte=il_y_a_7_jours,
            jour_prevu__lte=aujourd_hui,
            est_completee=True
        ).values('jour_prevu').annotate(sessions=Count('id'))

        # On prépare un dictionnaire pour s'assurer que les 7 jours sont présents (même ceux à 0)
        chart_data_dict = { (il_y_a_7_jours + timedelta(days=i)): 0 for i in range(7) }
        for s in seances_recentes:
            if s['jour_prevu'] in chart_data_dict:
                chart_data_dict[s['jour_prevu']] = s['sessions']

        # On formate la liste exactement comme React l'attend
        real_chart_data = [
            {"day": day.strftime("%a"), "sessions": count} 
            for day, count in chart_data_dict.items()
        ]

        # 4. Envoi de la réponse au front
        return Response({
            "total_athletes": total_athletes,
            "completion_rate": completion_rate,
            "total_volume": 0, # Mettre ici la logique de volume si tu as un modèle de charge soulevée
            "chart_data": real_chart_data
        })

class PerformanceCreateView(generics.CreateAPIView):
    serializer_class = PerformanceSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        # ON ENREGISTRE JUSTE LA SÉRIE, ON NE CLÔTURE PLUS LA SÉANCE ICI
        serializer.save(client=self.request.user.client_profile)

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        user = authenticate(username=request.data.get("email"), password=request.data.get("password"))
        if not user: return Response({"error": "Invalid credentials"}, status=401)
        refresh = RefreshToken.for_user(user)
        role = 'coach' if hasattr(user, 'coach_profile') else 'athlete' if hasattr(user, 'client_profile') else 'prospect'
        return Response({
            "token": str(refresh.access_token),
            "user": {"id": user.id, "email": user.email, "role": role}
        })

class CoachCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, coach_id=None):
        if hasattr(request.user, 'coach_profile'):
            coach = request.user.coach_profile
        else:
            coach = get_object_or_404(Coach, id=coach_id)
            
        seances = Seance.objects.filter(coach=coach).prefetch_related('inscriptions__client')
        
        data = []
        for s in seances:
            inscriptions = s.inscriptions.all()
            
            # --- Ta logique de nom d'athlète (restaurée) ---
            if s.est_collective:
                noms = [f"{ins.client.prenom} {ins.client.nom.upper()}" for ins in inscriptions]
                client_display = ", ".join(noms) if noms else "Aucun inscrit"
            else:
                athlete = s.programme.athlete if s.programme else None
                client_display = f"{athlete.prenom} {athlete.nom.upper()}" if athlete else "En attente"

            # --- Formatage pour FullCalendar (indispensable) ---
            start_dt = f"{s.jour_prevu}T{s.heure_debut}" if s.heure_debut else str(s.jour_prevu)
            end_dt = f"{s.jour_prevu}T{s.heure_fin}" if s.heure_fin else start_dt

            data.append({
                "id": s.id,
                "db_id": s.id,
                "title": s.titre,
                "start": start_dt,
                "end": end_dt,
                "client_name": client_display,
                "is_collective": s.est_collective,
                "est_collective": s.est_collective,
                "completed": s.est_completee,
                "est_completee": s.est_completee,
                "capacite_max": s.capacite_max,
                "nombre_inscrits": inscriptions.filter(statut='CONFIRME').count(),
                "type": "collective" if s.est_collective else "individuelle",
                "participants": [
                    {
                        "id": ins.id,
                        "client_id": ins.client.id,
                        "client_name": f"{ins.client.prenom} {ins.client.nom}",
                        "statut": ins.statut,
                        "date_inscription": ins.date_inscription.isoformat() if ins.date_inscription else None,
                    } for ins in inscriptions
                ]
            })
        return Response(data)

class IndisponibiliteViewSet(viewsets.ModelViewSet):
    serializer_class = IndisponibiliteSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        # On ne voit que ses propres indispos
        if hasattr(self.request.user, 'coach_profile'):
            return Indisponibilite.objects.filter(coach=self.request.user.coach_profile)
        return Indisponibilite.objects.none()

    # --- AJOUTE CE BLOC ICI ---
    def perform_create(self, serializer):
        # On force l'enregistrement du coach connecté
        if hasattr(self.request.user, 'coach_profile'):
            serializer.save(coach=self.request.user.coach_profile)
        else:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Seul un coach peut créer une indisponibilité.")

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_inscription_status(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    ancien_statut = ins.statut
    nouveau_statut = request.data.get('statut')
    
    # Mise à jour directe en BDD sans déclencher full_clean ni les signaux
    Inscription.objects.filter(id=inscription_id).update(statut=nouveau_statut)
    
    # Recharger l'objet pour avoir les données à jour
    ins.refresh_from_db()
    
    # Notification si passage liste d'attente → confirmé
    if ancien_statut == 'ATTENTE' and nouveau_statut == 'CONFIRME':
        client_name = f"{ins.client.prenom} {ins.client.nom}"
        Notification.objects.create(
            coach=ins.seance.coach,
            seance=ins.seance,
            message=f"{client_name} a été promu(e) de la liste d'attente et est maintenant confirmé(e) pour : {ins.seance.titre}",
            type='INSCRIPTION'
        )
    
    return Response({"status": "ok"})

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_participant(request, inscription_id):
    ins = get_object_or_404(Inscription, id=inscription_id)
    
    # On sauvegarde les infos AVANT suppression
    coach = ins.seance.coach
    client_name = f"{ins.client.prenom} {ins.client.nom}"
    seance = ins.seance
    seance_titre = ins.seance.titre
    
    # Suppression propre sans signal
    ins.delete()
    
    # Notification créée manuellement ici
    Notification.objects.create(
        coach=coach,
        seance=seance,
        message=f"{client_name} s'est désinscrit de la séance : {seance_titre}",
        type='DESINSCRIPTION'
    )
    
    return Response(status=204)

@api_view(['GET'])
@permission_classes([AllowAny])
def export_coach_calendar(request, coach_id):
    return HttpResponse("Flux iCal en construction", content_type="text/calendar")

class DemoStatsView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        return Response({
            "total_exercices": Exercice.objects.count(), 
            "total_coachs": Coach.objects.count()
        })


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Sécurité : Un coach ne voit QUE ses propres notifications
        if hasattr(self.request.user, 'coach_profile'):
            return Notification.objects.filter(coach=self.request.user.coach_profile)
        return Notification.objects.none()

    @action(detail=False, methods=['POST'])
    def marquer_tout_lu(self, request):
        # Cette fonction sera appelée quand le coach cliquera sur "Tout marquer comme lu"
        notifications = self.get_queryset().filter(est_lu=False)
        notifications.update(est_lu=True)
        return Response({'status': 'Toutes les notifications ont été marquées comme lues', 'count': notifications.count()})