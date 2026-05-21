from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Coach, Salle, Seance, ResponsableSalle


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
		# Responsable
		admin = User.objects.create(username='resp')
		ResponsableSalle.objects.create(user=admin, salle=self.salle)
		self.coach = coach

	def test_notification_created_on_seance_creation(self):
		seance = Seance.objects.create(coach=self.coach, titre='Test', jour_prevu=timezone.now().date(), salle=self.salle)
		# vérifier qu'une notification existe liée à la séance
		from .models import Notification
		notif = Notification.objects.filter(seance=seance).first()
		self.assertIsNotNone(notif)
		self.assertIn('Nouvelle séance planifiée', notif.message)
