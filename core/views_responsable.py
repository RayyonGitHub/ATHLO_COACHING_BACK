from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import ResponsableSalle, Seance, Inscription, Commande
from datetime import datetime
from django.db.models import Sum
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

        # 7. Revenus générés aujourd'hui (Ventes des coachs affiliés à cette salle)
        coachs_salle = salle.coachs_affilies.all()
        revenus = sum(
            c.montant_ttc for c in Commande.objects.filter(
                coach__in=coachs_salle, 
                status='PAID',
                date_commande__date=aujourd_hui
            )
        )

        return Response({
            "salle_nom": salle.nom,
            "kpis": {
                "seances_jour": nb_seances_jour,
                "coachs_actifs": coachs_actifs,
                "clients_presents": clients_presents,
                "taux_occupation": round(taux_occupation, 1),
                "reservations_attente": reservations_attente,
                "cours_complets": cours_complets,
                "revenus_generes": revenus
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