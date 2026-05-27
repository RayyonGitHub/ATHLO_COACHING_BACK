from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import ResponsableSalle, Seance, Inscription, Commande, ClientInvitation, NotificationResponsable, Coach, Coach
from datetime import datetime
from django.db.models import Sum, Count, Q
from django.db.models.functions import ExtractHour
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User

class ResponsableDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Vous n'êtes pas assigné comme responsable de salle."}, status=403)

        aujourd_hui = timezone.now().date()

        # 1. Séances du jour
        seances_jour = Seance.objects.filter(salle=salle, jour_prevu=aujourd_hui)
        nb_seances_jour = seances_jour.count()

        # 2. Nombre de coachs actifs
        coachs_actifs = seances_jour.values('coach').distinct().count()

        # 3. Clients présents
        clients_presents = Inscription.objects.filter(
            seance__in=seances_jour,
            statut__in=['CONFIRME', 'PRESENT']
        ).count()

        # 4. Taux d'occupation des salles
        capacite_totale = sum(s.capacite_max for s in seances_jour)
        taux_occupation = (clients_presents / capacite_totale * 100) if capacite_totale > 0 else 0

        # 5. Réservations en attente
        reservations_attente = Inscription.objects.filter(
            seance__salle=salle,
            statut='ATTENTE'
        ).count()

        # 6. Cours complets
        cours_complets = sum(
            1 for s in seances_jour 
            if s.inscriptions.filter(statut__in=['CONFIRME', 'PRESENT']).count() >= s.capacite_max
        )

        # 7. Revenus générés aujourd'hui
        coachs_salle = salle.coachs_affilies.all()

        # Abonnements prospects (Commande avec offre_type rempli)
        revenus_abonnements = sum(
            c.montant_ttc for c in Commande.objects.filter(
                coach__in=coachs_salle,
                status='PAID',
                date_commande__date=aujourd_hui
            ).exclude(Q(offre_type__isnull=True) | Q(offre_type=''))
        )

        # Boutique et extras (Commande sans offre_type = achats produits)
        revenus_boutique = sum(
            c.montant_ttc for c in Commande.objects.filter(
                coach__in=coachs_salle,
                status='PAID',
                date_commande__date=aujourd_hui
            ).filter(Q(offre_type__isnull=True) | Q(offre_type=''))
        )

        revenus_generes = revenus_abonnements + revenus_boutique

        return Response({
            "salle_nom": salle.nom,
            "kpis": {
                "seances_jour": nb_seances_jour,
                "coachs_actifs": coachs_actifs,
                "clients_presents": clients_presents,
                "taux_occupation": round(taux_occupation, 1),
                "reservations_attente": reservations_attente,
                "cours_complets": cours_complets,
                "revenus_generes": revenus_generes,
                "revenus_abonnements": revenus_abonnements,
                "revenus_boutique": revenus_boutique
            }
        })

class ResponsablePlanningView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Vous n'êtes pas assigné comme responsable de salle."}, status=403)

        # Récupération de la date (Aujourd'hui par défaut)
        date_str = request.query_params.get('date')
        if date_str:
            try:
                date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                date_cible = timezone.now().date()
        else:
            date_cible = timezone.now().date()

        # Récupérer les séances de CETTE salle, pour CETTE date
        seances = Seance.objects.filter(salle=salle, jour_prevu=date_cible).select_related('coach__user').order_by('heure_debut')

        # Formater les données
        planning_data = []
        for s in seances:
            planning_data.append({
                "id": s.id,
                "titre": s.titre,
                "heure_debut": s.heure_debut.strftime('%H:%M') if s.heure_debut else "00:00",
                "heure_fin": s.heure_fin.strftime('%H:%M') if s.heure_fin else "00:00",
                "coach_id": s.coach.id if s.coach else None,
                "coach_nom": f"{s.coach.user.first_name} {s.coach.user.last_name}" if s.coach else "Sans coach",
                "capacite_max": s.capacite_max,
                "inscrits_count": s.inscriptions.filter(statut__in=['CONFIRME', 'PRESENT']).count()
            })

        return Response({
            "salle_nom": salle.nom,
            "date": date_cible.isoformat(),
            "seances": planning_data
        })
        
class ResponsableCoachSupervisionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
        except Exception:
            return Response({"error": "Vous n'êtes pas assigné comme responsable de salle."}, status=403)

        aujourd_hui = timezone.now().date()
        debut_mois = aujourd_hui.replace(day=1)

        # Récupérer les coachs affiliés à cette salle
        coachs = salle.coachs_affilies.all()
        coach_data = []

        for coach in coachs:
            # Séances du coach DANS CETTE SALLE
            seances_jour = Seance.objects.filter(coach=coach, salle=salle, jour_prevu=aujourd_hui)
            seances_mois = Seance.objects.filter(coach=coach, salle=salle, jour_prevu__gte=debut_mois)

            nb_seances_jour = seances_jour.count()
            nb_seances_mois = seances_mois.count()

            # Calcul du taux d'occupation pour ce coach ce mois-ci
            capacite_totale = sum(s.capacite_max for s in seances_mois)
            inscrits_total = Inscription.objects.filter(seance__in=seances_mois, statut__in=['CONFIRME', 'PRESENT']).count()
            taux_occupation = (inscrits_total / capacite_totale * 100) if capacite_totale > 0 else 0

            # Estimation des revenus générés (via Commandes)
            revenus_mois = Commande.objects.filter(
                coach=coach, 
                status='PAID', 
                date_commande__gte=debut_mois
            ).aggregate(total=Sum('montant_ttc'))['total'] or 0

            # Détermination de l'indice d'activité (juste pour le visuel)
            if taux_occupation >= 90:
                index_color = "text-[#ff7351]" # Critical
                index_text = f"Maximum ({round(taux_occupation)}%)"
            elif taux_occupation >= 70:
                index_color = "text-[#ff915a]" # High
                index_text = f"Élevé ({round(taux_occupation)}%)"
            elif taux_occupation > 0:
                index_color = "text-[#acaab0]" # Optimal
                index_text = f"Optimal ({round(taux_occupation)}%)"
            else:
                index_color = "text-[#48474c]" # Low
                index_text = "Faible / Aucun"

            coach_data.append({
                "id": coach.id,
                "nom": f"{coach.user.first_name} {coach.user.last_name}",
                "seances_jour": nb_seances_jour,
                "seances_mois": nb_seances_mois,
                "taux_occupation": round(taux_occupation, 1),
                "revenus_generes": revenus_mois,
                "index_color": index_color,
                "index_text": index_text
            })

        # Calculer les KPIs globaux pour le haut de page
        total_revenus = sum(c['revenus_generes'] for c in coach_data)
        coachs_actifs_jour = sum(1 for c in coach_data if c['seances_jour'] > 0)

        return Response({
            "salle_nom": salle.nom,
            "kpis": {
                "total_commissions": total_revenus,
                "coachs_actifs_jour": coachs_actifs_jour,
                "total_coachs": coachs.count()
            },
            "coachs": coach_data
        })

class ResponsableStatistiquesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
        except Exception:
            return Response({"error": "Vous n'êtes pas assigné comme responsable de salle."}, status=403)

        aujourd_hui = timezone.now().date()
        debut_mois = aujourd_hui.replace(day=1)

        # 1. Toutes les séances du mois pour cette salle
        seances_mois = Seance.objects.filter(salle=salle, jour_prevu__gte=debut_mois, jour_prevu__lte=aujourd_hui)

        # 2. Fréquentation (inscriptions confirmées ou présentes)
        inscriptions_mois = Inscription.objects.filter(
            seance__in=seances_mois, 
            statut__in=['CONFIRME', 'PRESENT']
        )
        frequentation_totale = inscriptions_mois.count()

        # 3. Taux de remplissage global du mois
        capacite_totale = sum(s.capacite_max or 0 for s in seances_mois)
        taux_remplissage = (frequentation_totale / capacite_totale * 100) if capacite_totale > 0 else 0

        # 4. Heures de pointe (On groupe par heure de début et on compte le nombre de séances)
        # Note: Pour SQLite/PostgreSQL, ExtractHour extrait l'heure.
        heures_data = seances_mois.annotate(
            heure=ExtractHour('heure_debut')
        ).values('heure').annotate(
            nb_seances=Count('id')
        ).order_by('-nb_seances')[:3]
        
        heures_pointe = [
            {"heure": f"{h['heure']}h00", "nb_seances": h['nb_seances']} 
            for h in heures_data if h['heure'] is not None
        ]

        # 5. Top 5 des coachs les plus actifs (par nombre de séances)
        top_coachs_data = seances_mois.values(
            'coach__user__first_name', 
            'coach__user__last_name'
        ).annotate(
            total_seances=Count('id')
        ).order_by('-total_seances')[:5]

        top_coachs = [
            {
                "nom": f"{c['coach__user__first_name']} {c['coach__user__last_name']}",
                "seances": c['total_seances']
            } for c in top_coachs_data if c['coach__user__first_name']
        ]

        # 6. Revenus générés ce mois-ci par les coachs de la salle
        from .models import Coach
        coachs_salle = Coach.objects.filter(salles=salle)
        revenus_mois = Commande.objects.filter(
            coach__in=coachs_salle, 
            status='PAID', 
            date_commande__gte=debut_mois
        ).aggregate(total=Sum('montant_ttc'))['total'] or 0

        return Response({
            "mois": debut_mois.strftime("%B %Y"),
            "frequentation": frequentation_totale,
            "taux_remplissage": round(taux_remplissage, 1),
            "revenus_mois": float(revenus_mois),
            "heures_pointe": heures_pointe,
            "top_coachs": top_coachs
        })

# --- NOUVELLES VUES POUR LES PARAMÈTRES (Format APIView) ---

class ResponsableMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=404)

        return Response({
            "id": responsable.id,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
            "telephone": responsable.telephone,
            "salle_nom": responsable.salle.nom
        })

    def patch(self, request):
        try:
            responsable = request.user.responsable_profile
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=404)
        
        data = request.data
        user = request.user
        
        # Mise à jour des infos User
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.save()
        
        # Mise à jour des infos Profil
        responsable.telephone = data.get('telephone', responsable.telephone)
        responsable.save()
        
        return Response({"message": "Profil mis à jour avec succès"})

class ResponsableChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not user.check_password(old_password):
            return Response({"error": "Ancien mot de passe incorrect"}, status=400)
        
        user.set_password(new_password)
        user.save()
        return Response({"message": "Mot de passe modifié avec succès"})


class ResponsableNotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)
        
        from .serializers import NotificationResponsableSerializer
        notifications = NotificationResponsable.objects.filter(responsable=responsable).order_by('-date_creation')[:50]
        serializer = NotificationResponsableSerializer(notifications, many=True)
        return Response(serializer.data)


class ResponsableNotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            responsable = request.user.responsable_profile
            notif = NotificationResponsable.objects.get(id=pk, responsable=responsable)
            notif.est_lu = request.data.get('est_lu', True)
            notif.save()
            return Response({"message": "Notification mise à jour"})
        except NotificationResponsable.DoesNotExist:
            return Response({"error": "Notification introuvable."}, status=404)
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)


class ResponsableCoachListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)
        
        coachs = salle.coachs_affilies.all()
        data = []
        for coach in coachs:
            data.append({
                "id": coach.id,
                "nom": f"{coach.user.first_name} {coach.user.last_name}",
                "email": coach.user.email,
                "telephone": coach.telephone,
                "ville": coach.ville,
                "specialite": coach.specialite,
                "specialites_tags": coach.specialites_tags
            })
        return Response(data)


class ResponsableCoachDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, coach_id):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
            coach = Coach.objects.get(id=coach_id, salles=salle)
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)
        except Coach.DoesNotExist:
            return Response({"error": "Coach non trouvé ou non affilié à votre salle."}, status=404)
        
        return Response({
            "id": coach.id,
            "prenom": coach.user.first_name,
            "nom": coach.user.last_name,
            "email": coach.user.email,
            "telephone": coach.telephone,
            "ville": coach.ville,
            "specialite": coach.specialite,
            "specialites_tags": coach.specialites_tags
        })
    
    def patch(self, request, coach_id):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
            coach = Coach.objects.get(id=coach_id, salles=salle)
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)
        except Coach.DoesNotExist:
            return Response({"error": "Coach non trouvé ou non affilié à votre salle."}, status=404)
        
        coach.telephone = request.data.get('telephone', coach.telephone)
        coach.ville = request.data.get('ville', coach.ville)
        coach.specialite = request.data.get('specialite', coach.specialite)
        if 'specialites_tags' in request.data:
            coach.specialites_tags = request.data.get('specialites_tags')
        coach.save()
        
        user = coach.user
        user.first_name = request.data.get('prenom', user.first_name)
        user.last_name = request.data.get('nom', user.last_name)
        user.save()
        
        return Response({"message": "Coach mis à jour avec succès"})
    
    def delete(self, request, coach_id):
        try:
            responsable = request.user.responsable_profile
            salle = responsable.salle
            coach = Coach.objects.get(id=coach_id, salles=salle)
        except ResponsableSalle.DoesNotExist:
            return Response({"error": "Profil responsable introuvable."}, status=403)
        except Coach.DoesNotExist:
            return Response({"error": "Coach non trouvé ou non affilié à votre salle."}, status=404)
        
        coach.salles.remove(salle)
        salle.coachs_bannis.add(coach)
        return Response({"message": "Coach définitivement retiré de la salle"})