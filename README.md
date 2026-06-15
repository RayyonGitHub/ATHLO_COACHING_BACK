# Athlo - Back-End

Ce dépôt contient le **Back-End** de l'application **Athlo**, développé avec **Django 5.2** et **Django REST Framework**.

Il expose une **API REST** sécurisée (JWT) pour que les clients Front-End Web et Mobile puissent interagir avec les données de la plateforme.

---

## Contexte du projet

Le projet fait partie du programme **ArchiWeb 2026** et fournit l'architecture serveur complète pour gérer :

- Coaches, clients, prospects et responsables de salle
- Séances, programmes d'entraînement et exercices
- Contrats, paiements Stripe et facturation PDF
- Boutique en ligne (produits physiques et numériques)
- Nutrition (recettes et plans nutritionnels)
- Messagerie interne et notifications
- Intégrations tierces (Stripe, Strava, Google Calendar)

---

## Rôles utilisateurs

| Rôle | Description |
| ---- | ----------- |
| **Coach** | Gère clients, séances, programmes, boutique, dévis et finances |
| **Athlete (Client)** | Consulte ses séances, programmes, statistiques et commandes |
| **Prospect** | Découvre les coachs, demande des devis et s'inscrit |
| **Responsable** | Supervise les coachs et le planning d'une salle de sport |
| **Admin** | Administre l'ensemble de la plateforme (superuser Django) |

---

## Stack technique

| Catégorie | Technologie | Version |
| --------- | ----------- | ------- |
| Langage | Python | 3.11+ |
| Framework web | Django | 5.2.11 |
| API REST | Django REST Framework | 3.16.1 |
| Authentification | djangorestframework-simplejwt | 5.5.1 |
| CORS | django-cors-headers | 4.9.0 |
| Filtrage | django-filter | 25.2 |
| Paiements | stripe | 15.1.0 |
| Calendrier | icalendar | 7.0.3 |
| Images | Pillow | 12.2.0 |
| PDF | reportlab | 4.5.0 |
| Tâches planifiées | APScheduler | 3.11.2 |
| Variables d'env | python-dotenv | 1.2.2 |
| Base de données (dev) | SQLite 3 | — |
| Base de données (prod) | PostgreSQL | — |

---

## Fonctionnement général

- Le back-end expose **plus de 100 endpoints REST** répartis par domaine fonctionnel
- Les rôles et permissions sont gérés via des classes de permissions Django REST Framework personnalisées
- Tous les endpoints sont sécurisés par JWT (sauf login, register et endpoints publics)
- Un mécanisme de **refresh automatique** du token est pris en charge côté client
- Les paiements sont traités via **Stripe** (webhooks, PaymentIntent, Stripe Connect)
- Les **signaux Django** automatisent les inscriptions, les notifications et la synchronisation calendrier

---

## Intégrations tierces

| Service | Usage |
| ------- | ----- |
| **Stripe** | Abonnements coaches, achats athlètes, boutique, Stripe Connect (reversements) |
| **Strava** | Synchronisation des activités sportives de l'athlète via OAuth |
| **Google Calendar** | Export des séances du coach vers Google Calendar via OAuth |
| **Gmail SMTP** | Envoi d'emails (reset de mot de passe, invitations clients) |
| **ReportLab** | Génération de factures PDF |

---

## Documentation

- [docs/installation.md](docs/installation.md) — installation, configuration et lancement en local
- [docs/architecture.md](docs/architecture.md) — architecture N-tiers, choix techniques et flux de données
- [docs/modele_donnees.md](docs/modele_donnees.md) — schéma des données, entités et relations

---

## Maquette

<https://stitch.withgoogle.com/projects/15655097857567584238>

---

## Auteur

- **Groupe 6 ArchiWeb 2026**
