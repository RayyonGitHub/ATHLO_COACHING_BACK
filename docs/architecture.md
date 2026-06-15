# Architecture du projet Athlo

## Contexte

Athlo est une plateforme de coaching sportif permettant à des coachs de gérer leur activité professionnelle : clients, séances, programmes d'entraînement, nutrition, boutique en ligne, messagerie, facturation et intégrations tierces.

La plateforme est accessible via :

- une **application web** (React + Tailwind CSS)
- une **application mobile** (Expo / React Native)
- une **API REST** exposée par ce back-end Django

---

## Architecture N-tiers

Le projet suit une **architecture N-tiers** avec séparation claire des couches.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Couche Présentation                         │
│                                                                 │
│   Front-End Web (React 19 + Vite)    App Mobile (Expo/RN)      │
│   http://localhost:5173              http://localhost:8081      │
└───────────────────────┬────────────────────────┬───────────────┘
                        │    Requêtes HTTP/REST   │
                        │    JWT Authorization    │
                        ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Couche Logique Métier                       │
│                                                                 │
│   Django 5.2 + Django REST Framework 3.16.1                    │
│   http://localhost:8000/api/                                    │
│                                                                 │
│   • Authentification & autorisation (JWT, rôles)               │
│   • Validation des données (serializers)                       │
│   • Règles métier (vues, services)                             │
│   • Tâches planifiées (APScheduler)                            │
│   • Signaux Django (automatisations)                           │
│   • Intégrations tierces (Stripe, Strava, Google, Email)       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Couche Données                              │
│                                                                 │
│   SQLite (développement)  /  PostgreSQL (production)           │
│                                                                 │
│   25+ modèles Django                                           │
│   Migrations gérées par Django                                 │
│   Fichiers médias stockés dans /media/                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Organisation du code source

```text
endyearproject_2026_back/
├── archiweb_back/          # Configuration Django (settings, urls, wsgi, asgi)
├── core/                   # Application principale
│   ├── models.py           # Tous les modèles de données
│   ├── serializers.py      # Sérialisation des données (REST)
│   ├── serializers_*.py    # Serializers spécialisés (messages, nutrition, prospect)
│   ├── views.py            # Endpoints principaux (coach, athlete, sessions...)
│   ├── views_auth.py       # Authentification (login, register, reset)
│   ├── views_admin.py      # Administration (KPIs, gestion utilisateurs)
│   ├── views_stripe.py     # Paiements Stripe (PaymentIntent, Connect, webhooks)
│   ├── views_messages.py   # Messagerie (conversations, messages)
│   ├── views_nutrition.py  # Nutrition (recettes, plans)
│   ├── views_prospect.py   # Marketplace (discovery, checkout prospect)
│   ├── views_shop.py       # Boutique (produits, commandes)
│   ├── views_responsable.py# Espace responsable de salle
│   ├── views_integrations.py # Strava / Garmin
│   ├── views_google.py     # Google Calendar
│   ├── permissions.py      # Classes de permissions par rôle
│   ├── tasks.py            # Tâches planifiées (rappels automatiques)
│   ├── contract_utils.py   # Gestion des contrats athlètes
│   ├── email_utils.py      # Envoi d'emails HTML
│   ├── invoice_utils.py    # Génération de factures PDF (ReportLab)
│   ├── integrations_service.py # Service Strava / Garmin
│   ├── google_calendar.py  # Service Google Calendar
│   └── google_signals.py   # Signaux pour sync Google Calendar
├── docs/                   # Documentation
├── media/                  # Fichiers uploadés (messages, produits, factures)
└── requirements.txt        # Dépendances Python
```

---

## Rôles et permissions

Le back-end gère **5 rôles** avec des permissions distinctes :

| Rôle | Profil Django | Accès |
| ---- | ------------- | ----- |
| **Coach** | `coach_profile` (OneToOne) | Gestion clients, séances, programmes, boutique, finances |
| **Athlete** | `client_profile` (OneToOne) | Séances, programmes, statistiques, achats |
| **Prospect** | Aucun profil | Découverte coaches, devis, checkout |
| **Responsable** | `responsable_profile` (OneToOne) | Supervision salle, coachs affiliés |
| **Admin** | Django superuser | Accès complet à tout |

L'autorisation est vérifiée dans chaque vue via des classes de permissions personnalisées (`core/permissions.py`) et des contrôles explicites sur `request.user`.

---

## Authentification JWT

**Bibliothèque :** `djangorestframework-simplejwt`

- **Token d'accès :** durée de vie 60 minutes
- **Token de rafraîchissement :** durée de vie 24 heures
- **Algorithme :** HS256
- **En-tête :** `Authorization: Bearer <access_token>`

**Flux d'authentification :**

```
Client → POST /api/auth/login/
       ← { token, refresh?, user: { id, email, role } }

Client → Requête API + Authorization: Bearer <token>
       ← Données ou 401

Client (401) → POST /api/auth/token/refresh/ + { refresh }
             ← { access: <nouveau_token> }

Client (refresh échoué) → Déconnexion et redirection vers /login
```

---

## Intégrations tierces

### Stripe

Gestion complète des paiements via l'API Stripe :

- **Abonnements coaches** : plans premium mensuels (`price_*`)
- **Achats athlètes** : packs de séances et séances à l'unité (PaymentIntent)
- **Boutique** : commandes de produits physiques et numériques
- **Stripe Connect** : reversements vers les coachs (onboarding, account status)
- **Webhooks** : confirmation des paiements (`payment_intent.succeeded`, `checkout.session.completed`, `customer.subscription.deleted`)
- **Facturation PDF** : générée automatiquement via ReportLab à la confirmation d'une commande

### Strava

Synchronisation des activités sportives des athlètes :

1. L'athlète initie la connexion OAuth via `/api/athlete/integrations/strava/connect/`
2. Strava redirige vers l'URL de callback avec un code d'autorisation
3. Le code est échangé contre des tokens d'accès (stockés sur le modèle `Client`)
4. La synchronisation (`/api/athlete/integrations/strava/sync/`) importe les 30 dernières activités
5. Les activités sont stockées dans le modèle `ActiviteExterne`

### Google Calendar

Synchronisation des séances du coach avec Google Calendar :

1. Le coach initie la connexion OAuth via `/api/google-calendar/connect/`
2. Google redirige avec un code d'autorisation
3. Les tokens sont stockés sur le modèle `Coach`
4. Les séances créées ou modifiées déclenchent automatiquement des événements Google Calendar via des signaux Django

### Emails (Gmail SMTP)

Envoi d'emails transactionnels via `email_utils.py` :

- Réinitialisation de mot de passe (lien tokenisé, validité 1 heure)
- Invitations clients (lien de paiement + création de compte)
- Confirmations de paiement

---

## Signaux Django (automatisations)

Les signaux `post_save` automatisent des actions métier sans code explicite dans les vues :

| Modèle | Signal | Action |
| ------ | ------ | ------ |
| `Seance` | `post_save` | Inscrit automatiquement l'athlète d'un programme lors de la création d'une séance |
| `Seance` | `post_save` | Déduit un crédit de séance du contrat de l'athlète |
| `Seance` | `post_save` | Notifie l'athlète de la nouvelle séance |
| `Seance` | `post_save` | Notifie le responsable de salle d'une nouvelle séance dans sa salle |
| `Seance` | `post_save` | Crée ou met à jour l'événement Google Calendar du coach |

---

## Tâches planifiées

Le module `APScheduler` exécute des tâches en arrière-plan :

- **`generer_rappels_automatiques`** : génère des rappels de séances pour la journée en cours (exécuté quotidiennement)

---

## Communication Front ↔ Back

- Les clients consomment les **endpoints REST** exposés par le back-end
- Toutes les requêtes (sauf endpoints publics) nécessitent un token JWT valide
- Le back-end assure la validation, la sécurité et les règles métier
- Les mises à jour front ou back sont indépendantes grâce à la séparation stricte des couches

---

## Déploiement

**Développement local :**

```bash
python manage.py runserver
# → http://127.0.0.1:8000
```

**Production :**

- Serveur : **Gunicorn** (WSGI) via systemd
- Reverse proxy : **Nginx**
- Base de données : **PostgreSQL**
- Déploiement : **GitHub Actions** (push sur `main` → SSH → pull → migrate → restart)
- Domaine : `athlo.duckdns.org`

Pour démarrer localement avec le front-end, suivre les instructions dans [installation.md](installation.md).
