from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from django.contrib.auth import authenticate

from rest_framework import viewsets, status, generics # Ajout de generics ici
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework.exceptions import PermissionDenied

# Ajout de Performance et PerformanceSerializer
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer

# partie création de client
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings

# --- Vues Existantes ---

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'coach_profile'):
            return Client.objects.filter(coach=self.request.user.coach_profile)
        return Client.objects.none()

    def generate_password(self, length=10):
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def perform_create(self, serializer):
        print(">>> perform_create appelé")  # debug

        coach_profile = self.request.user.coach_profile

        email = serializer.validated_data.get('email')

        # vérification si le client existe deja alors lié le prospect  au client
        existing_user = User.objects.filter(email=email).first()
        existing_client = Client.objects.filter(email=email).first()

        if existing_user and existing_client:
            # Cas : prospect déjà inscrit → on le transforme en client
            client = existing_client

            client.coach = coach_profile
            client.nom = serializer.validated_data.get('nom')
            client.prenom = serializer.validated_data.get('prenom')

            client.save()

            print(f"Prospect transformé en client : {email}")

            return  # IMPORTANT : on ne recrée pas de user

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

        serializer.save(
            coach=coach_profile,
            user=user
        )

        print(f"Compte créé pour {email} | Mot de passe temporaire : {temp_password}")
        send_mail(
            subject="Vos identifiants de connexion",
            message=f"""
        Bonjour {serializer.validated_data.get('prenom')},

        Votre compte a été créé par votre coach.

        Voici vos identifiants temporaires :

        Email : {email}
        Mot de passe : {temp_password}

        Vous pourrez vous connecter ici :
        http://localhost:5173/login

        Merci.
        """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except:
            return Response({"detail": "Client introuvable."}, status=404)

        # supprimer le user associé
        if instance.user:
            instance.user.delete()

        instance.delete()

        return Response(status=204)


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
            return Seance.objects.filter(programme__coach=user.coach_profile)
        elif hasattr(user, 'client_profile'):
            return Seance.objects.filter(programme__athlete=user.client_profile)
        return Seance.objects.none()

    @transaction.atomic 
    def create(self, request, *args, **kwargs):
        data = request.data
        programme_id = data.get('programme_id')
        titre = data.get('titre')
        exercices_data = data.get('exercices', [])

        if not programme_id or not titre:
            return Response({"error": "Le programme_id et le titre sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        programme = get_object_or_404(Programme, id=programme_id)

        if not hasattr(request.user, 'coach_profile') or programme.coach != request.user.coach_profile:
            raise PermissionDenied("Vous n'êtes pas autorisé à ajouter une séance à ce programme.")

        ordre_seance = Seance.objects.filter(programme=programme).count() + 1

        seance = Seance.objects.create(
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

        # 1. Trouver la prochaine séance non complétée
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
                "duree_estimee": nb_exos * 10 if nb_exos > 0 else 45,
                "calories_estimees": nb_exos * 80 if nb_exos > 0 else 450,
            }

        # 2. Trouver le programme actuel de l'athlète (NOUVEAU)
        programme_actuel = Programme.objects.filter(athlete=client).last()
        programme_data = None
        if programme_actuel:
            total_seances = Seance.objects.filter(programme=programme_actuel).count()
            seances_faites = Seance.objects.filter(programme=programme_actuel, est_completee=True).count()
            
            progression_globale = 0
            if total_seances > 0:
                progression_globale = int((seances_faites / total_seances) * 100)

            programme_data = {
                "titre": programme_actuel.titre,
                "progression": progression_globale,
                "semaine_actuelle": (seances_faites // 3) + 1 if total_seances > 0 else 1, # Simulation (3 séances/sem)
                "semaine_totale": (total_seances // 3) or 1
            }

        # 3. Calculs des performances du jour
        today = timezone.now().date()
        performances_du_jour = Performance.objects.filter(
            client=client,
            date_enregistrement__date=today
        )

        total_series_jour = sum(perf.series_realisees for perf in performances_du_jour)
        calories_brulees = total_series_jour * 15

        completion_jour = 0
        seance_du_jour = Seance.objects.filter(programme__athlete=client, jour_prevu=today).first()
        
        if seance_du_jour:
            total_exos_prevus = seance_du_jour.exercices_details.count()
            exos_valides = performances_du_jour.values('seance_exercice').distinct().count()
            
            if total_exos_prevus > 0:
                completion_jour = int((exos_valides / total_exos_prevus) * 100)
                if exos_valides >= total_exos_prevus and not seance_du_jour.est_completee:
                    seance_du_jour.est_completee = True
                    seance_du_jour.save()

        # 4. Calcul du BMR
        calories_max_objectif = 2400 
        if client.poids and client.taille and client.age:
            bmr = (10 * client.poids) + (6.25 * client.taille) - (5 * client.age) + 5
            calories_max_objectif = int(bmr * 1.55)

        # 5. Assemblage final
        data = {
            "prenom": client.prenom or user.username,
            "prochaine_seance": seance_data,
            "programme_actuel": programme_data, # <-- Injecté ici !
            "stats_sante": {
                "completion_jour": completion_jour,
                "calories": calories_brulees,
                "calories_max": calories_max_objectif,
                "recuperation": 94,
                "pas": 8432,   # Mock pour le moment
                "eau": 1.2     # Mock pour le moment
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

    def get(self, request):
        if not hasattr(request.user, 'coach_profile'):
            return Response({"error": "Réservé aux coachs"}, status=403)
            
        coach = request.user.coach_profile
        # Optimisation : on précharge les inscriptions et les clients pour éviter les requêtes N+1
        seances = Seance.objects.filter(
            programme__coach=coach
        ).prefetch_related('inscriptions__client')
        
        data = []
        for s in seances:
            inscriptions = s.inscriptions.all()
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
                "id": s.id,
                "title": s.titre,
                "start": f"{s.jour_prevu}T{s.heure_debut}" if s.heure_debut else str(s.jour_prevu),
                "is_collective": s.est_collective,
                "capacity_label": capacity_info,
                "client_name": client_display,
                "completed": s.est_completee
            })
        
        return Response(data)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(username=email, password=password)

        if user is None:
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        # DÉTECTION DU ROLE
        if hasattr(user, 'coach_profile'):
            role = 'coach'
        elif hasattr(user, 'client_profile'):
            role = 'athlete'
        else:
            role = 'prospect'

        return Response({
            "token": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "role": role
            }
        })