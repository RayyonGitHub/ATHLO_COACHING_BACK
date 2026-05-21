from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from .models import Coach, Notification, ResponsableSalle, Salle, Seance


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
