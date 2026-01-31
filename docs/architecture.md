# Architecture du projet Athlo 🏋️‍♂️

## Contexte

Athlo est une application web pour coachs sportifs permettant de gérer :

- Clients et prospects
- Séances et programmes
- Contenus métiers (exercices, plans nutritionnels)
- Messagerie interne
- Facturation et reporting
- Partenariats avec salles et autres coachs

L’objectif est de fournir un écosystème numérique complet et modulaire pour piloter toute l’activité d’un coach, en ligne, depuis n’importe quel appareil.

---

## Architecture N-tiers

Le projet suit une **architecture N-tiers** avec séparation claire Front-end / Back-end / Base de données.

**Couches :**
1. **Présentation (Front-End)**
   - React + Tailwind
   - Interaction avec l’utilisateur
   - Appels API REST pour récupérer ou modifier les données
2. **Logique métier (Back-End)**
   - Django + Django REST Framework
   - Gestion des utilisateurs, séances, programmes, contrats, paiements
   - Règles métier et permissions
3. **Données (Base de données)**
   - Modèles Django
   - Stockage des informations structurées (SQLite)
   - Gestion des relations entre entités (client, coach, séance, programme...)

## Choix techniques

- **Séparation front / back**
  - Front indépendant, peut évoluer ou être remplacé
  - Back exposant uniquement des API REST
- **Django REST Framework**
  - Rapidité de mise en place d’API REST
  - Authentification JWT intégrée
- **CORS activé**
  - Front et back hébergés séparément
  - Permet l’accès cross-domain sécurisé
- **React + Tailwind**
  - Réactivité et modularité
  - Composants réutilisables
- **Versioning et déploiement**
  - Dépôts séparés pour front et back
  - Possibilité de déployer chaque partie indépendamment

## Communication Front ↔ Back

- Les composants Front consomment les **endpoints REST** exposés par le Back.
- Le Back assure la validation des données, la sécurité et les règles métiers.
- Les mises à jour Front ou Back sont indépendantes grâce à cette séparation.

---

## Mise à jour pour coder

1. Suivre les instructions des fichiers `installation.md` pour configurer le front et le back
2. L'application sera accessible localement à l'URL suivante : http://localhost:5173