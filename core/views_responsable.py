from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import ResponsableSalle, Seance, Inscription, Commande
from datetime import datetime
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