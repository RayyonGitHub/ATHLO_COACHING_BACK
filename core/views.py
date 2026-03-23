from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
import datetime
from django.http import HttpResponse
from icalendar import Calendar, Event
from rest_framework.decorators import api_view, permission_classes,action
from rest_framework.permissions import AllowAny

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from django.contrib.auth import authenticate
from rest_framework import viewsets, status, generics
from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework.exceptions import PermissionDenied

# Ajout de Performance et PerformanceSerializer
from .models import Client, Coach, Exercice, Programme, Seance, SeanceExercice, Performance, Indisponibilite, Inscription, Notification
from .serializers import ClientSerializer, CoachSerializer, ExerciceSerializer, NotificationSerializer, ProgrammeSerializer, SeanceSerializer, PerformanceSerializer, IndisponibiliteSerializer, NotificationSerializer

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

      # 1. Trouver la prochaine séance non complétée (Individuelle OU Collective)
        prochaine_seance = Seance.objects.filter(
            Q(programme__athlete=client) | Q(inscriptions__client=client), # NOUVEAU : On gère les 2 cas !
            est_completee=False
        ).order_by('jour_prevu', 'heure_debut', 'ordre').first()

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

        # --- DÉBUT DES VRAIS CALCULS (ISSUE #17) ---
        
        today = timezone.now().date()
        
        # Récupérer toutes les performances du jour
        performances_du_jour = Performance.objects.filter(
            client=client,
            date_enregistrement__date=today
        )

        # Calcul des Calories brûlées
        total_series_jour = sum(perf.series_realisees for perf in performances_du_jour)
        calories_brulees = total_series_jour * 15

        # Calcul de la Complétion du jour (%)
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

        # 💡 NOUVEAU : Calcul Dynamique du BMR (Métabolisme) pour calories_max
        calories_max_objectif = 2400  # Valeur par défaut si profil incomplet
        
        if client.poids and client.taille and client.age:
            # Formule de Mifflin-St Jeor : (10 × Poids) + (6.25 × Taille) - (5 × Age) + 5
            bmr = (10 * client.poids) + (6.25 * client.taille) - (5 * client.age) + 5
            # On multiplie par 1.55 pour correspondre à une personne avec une activité sportive modérée
            calories_max_objectif = int(bmr * 1.55)

        # --- FIN DES CALCULS ---

        data = {
            "prenom": client.prenom or user.username,
            "prochaine_seance": seance_data,
            "stats_sante": {
                "completion_jour": completion_jour,
                "calories": calories_brulees,
                "calories_max": calories_max_objectif, # Vraie donnée basée sur le profil !
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

        # 1. Total des athlètes
        total_athletes = coach.clients.count()

        # 2. Calcul de la vraie ASSIDUITÉ (Présents vs Absents)
        inscriptions_terminees = Inscription.objects.filter(
            seance__coach=coach, 
            seance__est_completee=True,
            statut__in=['PRESENT', 'ABSENT']
        )
        presents = inscriptions_terminees.filter(statut='PRESENT').count()
        total_appels = inscriptions_terminees.count()
        
        assiduite = 0
        if total_appels > 0:
            assiduite = round((presents / total_appels) * 100)
        
        # 3. LE VRAI CALCUL DU VOLUME (Tonnage total sur les 7 derniers jours)
        # On récupère toutes les performances liées aux séances de ce coach cette semaine
        performances_7j = Performance.objects.filter(
            seance_exercice__seance__coach=coach,
            seance_exercice__seance__jour_prevu__range=[seven_days_ago, today]
        )
        
        total_volume = 0
        for perf in performances_7j:
            try:
                # Sécurité : on convertit en nombres pour éviter les crashs si le champ contient du texte
                poids = float(perf.poids_utilise) if perf.poids_utilise else 0
                series = int(perf.series_realisees) if perf.series_realisees else 0
                reps = int(perf.reps_realisees) if perf.reps_realisees else 0
                
                total_volume += (poids * series * reps)
            except (ValueError, TypeError):
                # Si le poids est "Poids du corps" (texte non convertible), on l'ignore dans le tonnage
                pass
                
        total_volume = round(total_volume) # On arrondit proprement
        
        # 4. Données du graphique
        chart_data = []
        jours_fr = {0: 'Lun', 1: 'Mar', 2: 'Mer', 3: 'Jeu', 4: 'Ven', 5: 'Sam', 6: 'Dim'}
        
        for i in range(7):
            date_target = seven_days_ago + timedelta(days=i)
            count_day = Seance.objects.filter(
                coach=coach,
                jour_prevu=date_target, 
                est_completee=True
            ).count()
            
            chart_data.append({
                "day": jours_fr[date_target.weekday()],
                "sessions": count_day
            })

        return Response({
            "total_athletes": total_athletes,
            "completion_rate": assiduite, 
            "total_volume": total_volume,  
            "chart_data": chart_data
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
            toutes_inscriptions = s.inscriptions.all()
            inscriptions_confirmees = s.inscriptions.filter(statut='CONFIRME')
            nb_inscrits = inscriptions_confirmees.count()
            participants_data = []
            for ins in toutes_inscriptions:
                participants_data.append({
                    "id": ins.id,
                    "client_name": f"{ins.client.prenom} {ins.client.nom.upper()}",
                    "statut": ins.statut,
                    # On convertit la date en texte si elle existe, sinon on met une date vide
                    "date_inscription": ins.date_inscription.isoformat() if hasattr(ins, 'date_inscription') else None
                })
            # ---------------------------------------------------------------------------

            # CAS 1 : Séance Collective (Groupe)
            if s.est_collective:
                noms_liste = [f"{ins.client.prenom} {ins.client.nom.upper()}" for ins in inscriptions_confirmees]
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
                    first_ins = inscriptions_confirmees.first()
                    client_display = f"{first_ins.client.prenom} {first_ins.client.nom.upper()}"
                    capacity_info = "1/1"
                else:
                    # Cas : pas d'athlète sur le programme et pas d'inscription
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
                "completed": s.est_completee,
                
                # 👇 VOILÀ CE QUI MANQUAIT POUR REACT ! 👇
                "capacite_max": s.capacite_max if s.capacite_max else 1,
                "nombre_inscrits": nb_inscrits,
                "participants": participants_data
                # 👆 --------------------------------- 👆
            })
            
        # 2. Traitement des Indisponibilités
        indispos = Indisponibilite.objects.filter(coach=coach)
        for ind in indispos:
            data.append({
                "id": f"indispo_{ind.id}",
                "db_id": ind.id,
                "title": ind.titre,
                "start": f"{ind.jour_prevu}T{ind.heure_debut}",
                "end": f"{ind.jour_prevu}T{ind.heure_fin}",
                "is_collective": False,
                "type": "conge" if ind.est_conge else "indisponibilite",
                "capacity_label": "",
                "client_name": "",
                "completed": False,
                
                # On met des valeurs vides pour que React ne crashe pas
                "capacite_max": 1,
                "nombre_inscrits": 0,
                "participants": []
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

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_participant(request, inscription_id):
    inscription = get_object_or_404(Inscription, id=inscription_id)
    
    if inscription.seance.coach.user != request.user:
        return Response({"error": "Vous n'avez pas le droit de modifier cette séance."}, status=403)
    
    seance = inscription.seance
    etait_confirme = (inscription.statut == 'CONFIRME')
    
    # 1. On supprime l'inscription
    inscription.delete()
    
    # 2. LOGIQUE DE LISTE D'ATTENTE (Auto-promotion)
    message = "Participant retiré de la séance."
    if etait_confirme and seance.est_collective:
        # On compte combien de confirmés il reste
        inscrits_count = seance.inscriptions.filter(statut='CONFIRME').count()
        
        # S'il y a de la place, on cherche le plus ancien en liste d'attente
        if inscrits_count < seance.capacite_max:
            premier_en_attente = seance.inscriptions.filter(statut='ATTENTE').order_by('date_inscription').first()
            
            if premier_en_attente:
                # On le promeut !
                premier_en_attente.statut = 'CONFIRME'
                premier_en_attente.save()
                message = f"Participant retiré. {premier_en_attente.client.prenom} a été automatiquement promu depuis la liste d'attente."
    
    return Response({"message": message}, status=200)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_inscription_status(request, inscription_id):
    inscription = get_object_or_404(Inscription, id=inscription_id)
    
    # Vérification de sécurité
    if inscription.seance.coach.user != request.user:
        return Response({"error": "Non autorisé"}, status=403)
        
    nouveau_statut = request.data.get('statut')
    
    # On autorise le passage en PRESENT ou ABSENT
    if nouveau_statut in ['PRESENT', 'ABSENT', 'CONFIRME']:
        inscription.statut = nouveau_statut
        inscription.save()
        return Response({"message": f"Statut mis à jour en {nouveau_statut}", "statut": nouveau_statut}, status=200)
        
    return Response({"error": "Statut invalide"}, status=400)

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