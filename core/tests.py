from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from .models import (
    ClientInvitation,
    Client,
    Commande,
    Coach,
    Exercice,
    Facture,
    Inscription,
    LigneCommande,
    Notification,
    Produit,
    ResponsableSalle,
    Salle,
    Seance,
    SeanceExercice,
)


class SallesFilteringTest(TestCase):
    def setUp(self):
        user = User.objects.create(username='coach1')
        self.coach = Coach.objects.create(user=user, ville='Amiens')
        self.s1 = Salle.objects.create(nom='Salle Amiens 1', adresse='addr', ville='Amiens')
        self.s2 = Salle.objects.create(nom='Salle Mulhouse', adresse='addr', ville='Mulhouse')
        self.coach.salles.add(self.s1, self.s2)

    def test_get_salles_filtered_by_coach_ville(self):
        from .views_prospect import _get_salles

        salles = _get_salles(self.coach)
        noms = [s['nom'] for s in salles]
        self.assertIn('Salle Amiens 1', noms)
        self.assertNotIn('Salle Mulhouse', noms)


class SeanceNotificationTest(TestCase):
    def setUp(self):
        user = User.objects.create(username='coach2')
        coach = Coach.objects.create(user=user, ville='Amiens')
        self.salle = Salle.objects.create(nom='Salle Amiens 2', adresse='addr', ville='Amiens')
        admin = User.objects.create(username='resp')
        ResponsableSalle.objects.create(user=admin, salle=self.salle)
        self.coach = coach

    def test_notification_created_on_seance_creation(self):
        seance = Seance.objects.create(
            coach=self.coach,
            titre='Test',
            jour_prevu=timezone.now().date(),
            salle=self.salle,
        )

        notif = Notification.objects.filter(seance=seance).first()
        self.assertIsNotNone(notif)
        self.assertIn('nouvelle seance planifiee', notif.message.lower().replace('é', 'e'))


class CoachSallesDisponiblesApiTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()
        self.user = User.objects.create_user(
            username='coach-city',
            email='coach-city@test.dev',
            password='x',
        )
        Coach.objects.create(user=self.user, ville='Amiens')
        self.client_api.force_authenticate(user=self.user)
        Salle.objects.create(nom='Salle Amiens', adresse='addr1', ville='Amiens')
        Salle.objects.create(nom='Salle Lille', adresse='addr2', ville='Lille')

    def test_endpoint_filters_by_coach_city(self):
        res = self.client_api.get('/api/coach/salles-disponibles/')
        self.assertEqual(res.status_code, 200)
        noms = [s['nom'] for s in res.json()]
        self.assertIn('Salle Amiens', noms)
        self.assertNotIn('Salle Lille', noms)


class ResponsablePlanningSeanceVisibilityTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()
        self.salle = Salle.objects.create(nom='Salle Responsable', adresse='addr', ville='Amiens')
        self.responsable_user = User.objects.create_user(
            username='resp-planning',
            email='resp@test.dev',
            password='x',
        )
        ResponsableSalle.objects.create(user=self.responsable_user, salle=self.salle)

        self.coach_user = User.objects.create_user(
            username='coach-planning',
            email='coach@test.dev',
            password='x',
        )
        Coach.objects.create(user=self.coach_user, ville='Amiens')

    def test_created_seance_with_salle_id_is_visible_for_responsable_planning(self):
        self.client_api.force_authenticate(user=self.coach_user)
        tomorrow_str = (timezone.now().date() + timedelta(days=1)).isoformat()
        create_payload = {
            'titre': 'Seance Athlete',
            'jour_prevu': tomorrow_str,
            'heure_debut': '10:00:00',
            'heure_fin': '11:00:00',
            'salle_id': self.salle.id,
        }
        create_res = self.client_api.post('/api/seances/', create_payload, format='json')
        self.assertEqual(create_res.status_code, 201)
        self.assertEqual(create_res.json().get('salle'), self.salle.id)

        self.client_api.force_authenticate(user=self.responsable_user)
        planning_res = self.client_api.get(f'/api/responsable/planning/?date={tomorrow_str}')
        self.assertEqual(planning_res.status_code, 200)

        seances = planning_res.json().get('seances', [])
        self.assertTrue(any(s.get('titre') == 'Seance Athlete' for s in seances))


class SeanceOwnershipGuardsTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()

        self.coach_owner_user = User.objects.create_user(username='coach-owner', password='x')
        self.coach_other_user = User.objects.create_user(username='coach-other', password='x')
        self.coach_owner = Coach.objects.create(user=self.coach_owner_user, ville='Amiens')
        Coach.objects.create(user=self.coach_other_user, ville='Lille')

        self.athlete_user = User.objects.create_user(username='athlete-ok', password='x')
        self.athlete_other_user = User.objects.create_user(username='athlete-no', password='x')
        self.athlete = Client.objects.create(
            user=self.athlete_user,
            coach=self.coach_owner,
            nom='Ok',
            prenom='Athlete',
            email='athlete-ok@test.dev',
        )
        self.athlete_other = Client.objects.create(
            user=self.athlete_other_user,
            coach=self.coach_owner,
            nom='No',
            prenom='Athlete',
            email='athlete-no@test.dev',
        )

        self.seance = Seance.objects.create(
            coach=self.coach_owner,
            titre='Seance Guard',
            jour_prevu=timezone.now().date(),
            capacite_max=10,
        )
        self.inscription = Inscription.objects.create(
            seance=self.seance,
            client=self.athlete,
            statut='CONFIRME',
        )

        ex = Exercice.objects.create(nom='Squat Guard')
        self.seance_ex = SeanceExercice.objects.create(seance=self.seance, exercice=ex)

    def test_update_inscription_status_forbidden_for_non_owner_coach(self):
        self.client_api.force_authenticate(user=self.coach_other_user)
        res = self.client_api.patch(
            f'/api/inscriptions/{self.inscription.id}/status/',
            {'statut': 'ATTENTE'},
            format='json',
        )
        self.assertEqual(res.status_code, 403)

    def test_remove_participant_forbidden_for_non_owner_coach(self):
        self.client_api.force_authenticate(user=self.coach_other_user)
        res = self.client_api.delete(f'/api/inscriptions/{self.inscription.id}/')
        self.assertEqual(res.status_code, 403)

    def test_record_performance_forbidden_for_non_inscribed_athlete(self):
        self.client_api.force_authenticate(user=self.athlete_other_user)
        payload = {
            'seance_id': self.seance.id,
            'exercices': [
                {
                    'exercice_id': self.seance_ex.exercice.id,
                    'series_realisees': 3,
                    'reps_realisees': 10,
                    'poids_moyen': 40,
                }
            ],
        }
        res = self.client_api.post('/api/athlete/performance/record/', payload, format='json')
        self.assertEqual(res.status_code, 403)

    def test_mark_seance_ratee_forbidden_for_non_inscribed_athlete(self):
        self.client_api.force_authenticate(user=self.athlete_other_user)
        res = self.client_api.post(f'/api/seances/{self.seance.id}/ratee/', {}, format='json')
        self.assertEqual(res.status_code, 403)


class CoachCalendarAccessTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()

        self.coach_a_user = User.objects.create_user(username='coach-a', password='x')
        self.coach_b_user = User.objects.create_user(username='coach-b', password='x')
        self.coach_a = Coach.objects.create(user=self.coach_a_user, ville='Amiens')
        self.coach_b = Coach.objects.create(user=self.coach_b_user, ville='Lille')

        athlete_user = User.objects.create_user(username='athlete-calendar', password='x')
        Client.objects.create(
            user=athlete_user,
            coach=self.coach_a,
            nom='Athlete',
            prenom='Calendar',
            email='athlete-calendar@test.dev',
        )
        self.athlete_user = athlete_user

        Seance.objects.create(
            coach=self.coach_a,
            titre='Seance Coach A',
            jour_prevu=timezone.now().date(),
        )

    def test_owner_coach_can_access_own_calendar(self):
        self.client_api.force_authenticate(user=self.coach_a_user)
        res = self.client_api.get(f'/api/calendar/coach/{self.coach_a.id}/')
        self.assertEqual(res.status_code, 200)

    def test_other_coach_cannot_access_foreign_calendar(self):
        self.client_api.force_authenticate(user=self.coach_b_user)
        res = self.client_api.get(f'/api/calendar/coach/{self.coach_a.id}/')
        self.assertEqual(res.status_code, 403)

    def test_athlete_cannot_access_coach_calendar(self):
        self.client_api.force_authenticate(user=self.athlete_user)
        res = self.client_api.get(f'/api/calendar/coach/{self.coach_a.id}/')
        self.assertEqual(res.status_code, 403)


class CreateOrderViewTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()

        coach_user = User.objects.create_user(username='coach-shop', password='x')
        self.coach = Coach.objects.create(user=coach_user, ville='Amiens')

        athlete_user = User.objects.create_user(username='athlete-shop', password='x')
        self.client_profile = Client.objects.create(
            user=athlete_user,
            coach=self.coach,
            nom='Shop',
            prenom='Athlete',
            email='athlete-shop@test.dev',
        )
        self.client_api.force_authenticate(user=athlete_user)

        self.produit = Produit.objects.create(
            coach=self.coach,
            nom='Produit Test',
            description='Desc',
            prix='19.99',
            stock=10,
        )

    def test_create_order_uses_montant_ttc_and_status_fields(self):
        payload = {
            'adresse_livraison': '1 rue test',
            'montant_ttc': 19.99,
            'lignes': [
                {
                    'produit_id': self.produit.id,
                    'quantite': 1,
                    'prix_unitaire': '19.99',
                }
            ],
        }
        res = self.client_api.post('/api/shop/orders/', payload, format='json')
        self.assertEqual(res.status_code, 201)
        commande_id = res.json().get('id')
        self.assertTrue(commande_id)
        self.assertTrue(LigneCommande.objects.filter(commande_id=commande_id).exists())

    def test_shop_my_orders_alias_returns_history(self):
        res = self.client_api.get('/api/shop/my-orders/')
        self.assertEqual(res.status_code, 200)


class InvitationSetPasswordFlowTest(TestCase):
    def setUp(self):
        self.client_api = APIClient()

        coach_user = User.objects.create_user(username='coach-invite', password='x')
        client_user = User.objects.create_user(
            username='athlete-invite',
            email='athlete-invite@test.dev',
            password='x',
        )
        self.coach = Coach.objects.create(user=coach_user, ville='Amiens')
        self.client_profile = Client.objects.create(
            user=client_user,
            coach=self.coach,
            nom='Invite',
            prenom='Athlete',
            email='athlete-invite@test.dev',
        )

    def test_set_password_creates_commande_and_facture_when_paid(self):
        invitation = ClientInvitation.objects.create(
            coach=self.coach,
            client=self.client_profile,
            email=self.client_profile.email,
            offer_type='abonnement',
            offer_label='Abonnement mensuel',
            amount=180,
            status='paid',
            payment_status='success',
            expires_at=timezone.now() + timedelta(days=1),
        )

        payload = {
            'token': str(invitation.token),
            'new_password': 'AthloTest#2026',
            'confirm_password': 'AthloTest#2026',
        }
        res = self.client_api.post('/api/prospects/invitations/set-password/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        commande = Commande.objects.filter(
            client=self.client_profile,
            coach=self.coach,
            offre_label='Abonnement mensuel',
            status='PAID',
        ).first()
        self.assertIsNotNone(commande)
        self.assertTrue(Facture.objects.filter(commande=commande).exists())

    def test_set_password_rejects_already_activated_invitation(self):
        invitation = ClientInvitation.objects.create(
            coach=self.coach,
            client=self.client_profile,
            email=self.client_profile.email,
            offer_type='abonnement',
            offer_label='Abonnement mensuel',
            amount=180,
            status='activated',
            payment_status='success',
            expires_at=timezone.now() + timedelta(days=1),
        )

        payload = {
            'token': str(invitation.token),
            'new_password': 'AthloTest#2026',
            'confirm_password': 'AthloTest#2026',
        }
        res = self.client_api.post('/api/prospects/invitations/set-password/', payload, format='json')
        self.assertEqual(res.status_code, 400)
