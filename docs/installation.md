# Installation du Back-End - Athlo

## Contexte

Ce dépôt contient le **Back-End** de l'application **Athlo**, développé avec **Django 6** et le **Django REST Framework**.  
Le back expose des API REST pour que le Front-End et d'autres clients puissent interagir avec les données (utilisateurs, séances, programmes, contrats, paiements, etc.).

---

## Prérequis

Avant de commencer, assurez-vous d’avoir installé :

- [Python 3.11+](https://www.python.org/)
- [pip](https://pip.pypa.io/en/stable/)
- [virtualenv](https://virtualenv.pypa.io/en/latest/)

---

## Étapes d'installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/uha-fr/archiweb_2026_projets_gr06_back.git
cd <nom_du_dossier_back>
git switch develop-back
```
### 2. Créer et activer l'environnement virtuel
# Windows
```bash
python -m venv venv
venv\Scripts\activate
```
# Mac / Linux
```bash
python -m venv venv
source venv/bin/activate
```
### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```
### Pour appliquer des migrations :
```bash
python manage.py makemigrations 

python manage.py migrate
```
### 4. Lancer le serveur
```bash
python manage.py runserver
```


Le serveur sera accessible par défaut à l'URL : http://127.0.0.1:8000

