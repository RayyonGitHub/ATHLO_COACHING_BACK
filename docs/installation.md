# Installation et configuration - Athlo Back-End

## Contexte

Ce dépôt contient le **Back-End** de l'application **Athlo**, développé avec **Django 5.2** et **Django REST Framework**.
Il expose une API REST sécurisée (JWT) pour les clients Front-End Web (`localhost:5173`) et Mobile (`localhost:8081`).

---

## Prérequis

Avant de commencer, assurez-vous d'avoir installé :

- [Python 3.11+](https://www.python.org/)
- [pip](https://pip.pypa.io/en/stable/)
- `virtualenv` : `pip install virtualenv`
- Git

---

## Étapes d'installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/uha-fr/endyearproject_2026_back.git
cd endyearproject_2026_back
```

### 2. Créer et activer l'environnement virtuel

**Windows :**

```bash
python -m venv venv
venv\Scripts\activate
```

**Mac / Linux :**

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

Créez un fichier `.env` à la racine du projet en vous basant sur `.env.example` :

```bash
cp .env.example .env
```

Renseignez ensuite les variables :

```env
# Django
SECRET_KEY=votre_cle_secrete_django
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:5173
CORS_ALLOW_ALL_ORIGINS=True
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8081

# Email (Gmail SMTP)
EMAIL_HOST_USER=votre_adresse@gmail.com
EMAIL_HOST_PASSWORD=votre_mot_de_passe_application
DEFAULT_FROM_EMAIL=votre_adresse@gmail.com

# Stripe
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Strava OAuth (optionnel)
STRAVA_CLIENT_ID=votre_strava_client_id
STRAVA_CLIENT_SECRET=votre_strava_client_secret
STRAVA_REDIRECT_URI=http://localhost:5173/auth/strava/callback

# Google Calendar OAuth (optionnel)
GOOGLE_CLIENT_ID=votre_google_client_id
GOOGLE_CLIENT_SECRET=votre_google_client_secret
```

> **Important :** Ne commitez jamais le fichier `.env` — il est listé dans `.gitignore`.
> En production, toutes les variables sensibles doivent être définies côté serveur ou via GitHub Secrets.

### 5. Appliquer les migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Créer un compte administrateur (optionnel)

```bash
python manage.py createsuperuser
```

Ce compte permet d'accéder à l'interface d'administration Django (`/admin/`) et aux endpoints `/api/admin/*`.

### 7. Lancer le serveur de développement

```bash
python manage.py runserver
```

Le serveur sera accessible à l'adresse : **`http://127.0.0.1:8000`**

L'interface d'administration Django est disponible à : **`http://127.0.0.1:8000/admin/`**

---

## Commandes utiles

| Commande | Description |
| -------- | ----------- |
| `python manage.py runserver` | Lance le serveur de développement |
| `python manage.py makemigrations` | Génère les fichiers de migration |
| `python manage.py migrate` | Applique les migrations à la base de données |
| `python manage.py createsuperuser` | Crée un administrateur Django |
| `python manage.py collectstatic` | Collecte les fichiers statiques (production) |
| `python manage.py shell` | Lance le shell Django interactif |

---

## Variables d'environnement — référence complète

| Variable | Obligatoire | Description |
| -------- | ----------- | ----------- |
| `SECRET_KEY` | Oui | Clé secrète Django (génère avec `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) |
| `DJANGO_DEBUG` | Non | Mode debug. Défaut : `True` (mettre `False` en production) |
| `DJANGO_ALLOWED_HOSTS` | Oui (prod) | Liste des hôtes autorisés séparés par des virgules |
| `FRONTEND_URL` | Oui | URL du front-end pour les liens dans les emails |
| `CORS_ALLOWED_ORIGINS` | Oui | Origines autorisées pour les appels CORS |
| `EMAIL_HOST_USER` | Oui (emails) | Adresse Gmail expéditrice |
| `EMAIL_HOST_PASSWORD` | Oui (emails) | Mot de passe d'application Gmail (pas votre mot de passe principal) |
| `STRIPE_PUBLIC_KEY` | Oui (paiements) | Clé publique Stripe |
| `STRIPE_SECRET_KEY` | Oui (paiements) | Clé secrète Stripe |
| `STRIPE_WEBHOOK_SECRET` | Oui (webhooks) | Secret de validation des webhooks Stripe |
| `STRAVA_CLIENT_ID` | Non | Client ID Strava pour l'OAuth |
| `STRAVA_CLIENT_SECRET` | Non | Client Secret Strava |
| `STRAVA_REDIRECT_URI` | Non | URL de callback Strava |
| `GOOGLE_CLIENT_ID` | Non | Client ID Google pour l'OAuth Calendar |
| `GOOGLE_CLIENT_SECRET` | Non | Client Secret Google |

---

## Base de données

**Développement :** SQLite (`db.sqlite3` à la racine du projet)

**Production :** PostgreSQL — configurer via la variable `DATABASE_URL` ou directement dans `settings.py`.

La base de données SQLite est légère et ne nécessite aucune configuration supplémentaire. Elle est suffisante pour le développement local.

---

## Configuration CORS

Le back-end est configuré pour accepter les requêtes des origines suivantes en développement :

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Front-End Web (Vite)
    "http://localhost:8081",   # App Mobile (Expo)
]
```

Pour simplifier le développement, vous pouvez temporairement activer `CORS_ALLOW_ALL_ORIGINS=True` dans le fichier `.env`.

---

## Déploiement (CI/CD)

Le déploiement est automatisé via **GitHub Actions** (`.github/workflows/deploy.yml`) :

1. Déclenchement sur push vers la branche `main`
2. Connexion SSH au VPS
3. `git pull` du dépôt
4. Activation de l'environnement virtuel
5. `pip install -r requirements.txt`
6. `python manage.py migrate`
7. `python manage.py collectstatic`
8. Redémarrage du service `gunicorn`

**Stack de production :**

- Serveur d'application : **Gunicorn** (WSGI)
- Reverse proxy : **Nginx** (recommandé)
- Base de données : **PostgreSQL**
- Domaine : `athlo.duckdns.org`

---

## Dépannage courant

**Erreur `ModuleNotFoundError` au démarrage :**

- Vérifiez que l'environnement virtuel est bien activé (`venv\Scripts\activate` sur Windows).
- Relancez `pip install -r requirements.txt`.

**Erreur CORS depuis le front-end :**

- Vérifiez que l'URL du front-end est bien dans `CORS_ALLOWED_ORIGINS` dans `.env`.
- Ou activez temporairement `CORS_ALLOW_ALL_ORIGINS=True`.

**Erreur lors des migrations :**

- Si des conflits de migration existent, supprimez `db.sqlite3` et relancez `migrate`.
- N'utilisez jamais cette méthode en production.

**Webhooks Stripe ne fonctionnent pas en local :**

- Utilisez [Stripe CLI](https://stripe.com/docs/stripe-cli) pour relayer les webhooks vers votre serveur local :
  `stripe listen --forward-to localhost:8000/api/stripe/webhook/`
