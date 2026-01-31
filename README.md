# Athlo - Back-End 

Ce dépôt contient le **Back-End** de l'application Athlo, développé avec **Django 6** et **Django REST Framework**.

Il expose des **API REST** pour que le Front-End et d'autres clients puissent interagir avec les données de l’application.

---

## Contexte du projet

Le projet fait partie du programme **ArchiWeb 2026** et vise à fournir une architecture serveur robuste pour gérer :

- Clients, coachs et prospects
- Séances, programmes et exercices
- Contrats, paiements et facturation
- Messagerie interne et notifications
- Intégration avec services tiers (Google Calendar, APIs fitness)

---

## Stack technique

- **Python 3.11+**
- **Django 6** – framework web
- **Django REST Framework** – API REST
- **django-cors-headers** – gestion CORS pour le Front
- **djangorestframework-simplejwt** – authentification JWT
- Base de données SQLite (dev) / PostgreSQL (prod)

---

## Fonctionnement général

- Le back fournit les endpoints REST pour toutes les entités principales (Utilisateur, Client, Coach, Séance, Programme, Contrat, Paiement, Message, etc.)
- Les rôles et permissions sont gérés côté back (Coach, Client, Prospect, Admin)
- Les endpoints sont sécurisés et authentifiés via JWT

---

## Documentations

- [installation.md](docs/installation.md) : décrit comment installer et configurer le Front et le Back pour que l’application fonctionne sur un poste de développement.
- [architecture.md](docs/architecture.md)  : explique le fonctionnement global de l’application et les choix techniques faits pour sa conception et son organisation.
- [modele_donnees.md](docs/modele_donnees.md) : présente le schéma des données et décrit chaque entité et ses relations dans l’application.

---

## Maquette

https://stitch.withgoogle.com/projects/15655097857567584238

---

## Auteur


- **Groupe 6 ArchiWeb 2026**

