# Modèle de données

Ce document décrit le modèle de données de l’application de gestion de coaching sportif.  
Il est basé sur les modèles Django implémentés dans le projet.

---

## 🧠 Vue d’ensemble

Le système repose sur deux types d’utilisateurs :
- des **coachs**
- des **clients**

Chaque utilisateur possède un compte (`User`) et un profil spécifique (`Coach` ou `Client`).

Le système gère :
- des programmes d’entraînement
- des séances
- des exercices
- les performances
- les inscriptions
- une messagerie interne
- des notifications
- des demandes de devis

---

## 📦 Entités principales

### 👤 User
Utilisateur de base géré par Django (authentification).

---

### 🧑‍🏫 Coach
Profil coach associé à un utilisateur.

- téléphone
- spécialité
- ville
- offres et tarifs (JSON)
- spécialités (tags JSON)
- tokens Google Calendar

---

### 🧑‍💼 Client
Profil client associé à un utilisateur.

- informations personnelles (nom, prénom, email…)
- données physiques (taille, poids…)
- objectifs sportifs
- pathologies
- niveau d’activité
- coach référent
- consentement RGPD
- données onboarding (JSON)

---

### 🏋️ Exercice
Définition d’un exercice sportif.

- nom
- catégorie
- description
- muscle principal
- lien vidéo

---

### 📋 Programme
Programme créé par un coach.

- titre
- description
- dates
- coach créateur
- client associé (optionnel)

---

### 🗓️ Séance
Séance d’entraînement.

- titre
- date / heure
- capacité
- statut (complétée ou non)
- coach
- programme associé (optionnel)

---

### 🔁 SéanceExercice
Détail des exercices dans une séance.

- nombre de séries
- répétitions
- poids
- temps de repos
- ordre

---

### 📊 Performance
Résultats réalisés par un client.

- séries effectuées
- répétitions
- poids utilisé
- notes

---

### ✅ Inscription
Participation d’un client à une séance.

- statut (confirmé, attente, absent…)
- gestion de la capacité maximale

---

### 🚫 Indisponibilité
Créneaux d’indisponibilité d’un coach.

---

### 🏢 Salle
Lieu physique.

- nom
- adresse
- ville
- coordonnées GPS

---

### ⭐ Avis
Avis donné par un client à un coach.

---

### 🔔 Notification (coach)
Notifications liées aux séances et événements.

---

### 🔔 NotificationAthlete (client)
Notifications spécifiques au client.

---

### 💬 Messagerie

#### Conversation
- type (direct ou groupe)
- créateur

#### ConversationParticipant
- participants d’une conversation

#### Message
- contenu
- expéditeur
- date

#### MessageAttachment
- fichiers joints

---

### 📄 Devis
Demande de devis envoyée à un coach.

- informations personnelles
- objectifs
- budget
- statut

---

## 🔗 Relations principales

- Un **User** possède :
  - 0 ou 1 **Coach**
  - 0 ou 1 **Client**

- Un **Coach** :
  - gère plusieurs **Clients**
  - crée plusieurs **Programmes**
  - planifie plusieurs **Séances**

- Un **Programme** :
  - contient plusieurs **Séances**
  - peut être assigné à un **Client**

- Une **Séance** :
  - contient plusieurs **SéanceExercice**
  - possède plusieurs **Inscriptions**

- Un **Client** :
  - réalise des **Performances**
  - s’inscrit à des **Séances**
  - reçoit des **Notifications**

- Une **Conversation** :
  - contient plusieurs **Messages**
  - possède plusieurs participants

---

## 📊 Diagramme (Mermaid)

```mermaid
classDiagram

    User --> Coach
    User --> Client

    Coach --> Client
    Coach --> Programme
    Coach --> Seance

    Programme --> Seance

    Seance --> SeanceExercice
    Exercice --> SeanceExercice

    Client --> Performance
    SeanceExercice --> Performance

    Client --> Inscription
    Seance --> Inscription

    Coach --> Indisponibilite
    Coach --> Avis
    Client --> Avis

    Conversation --> Message
    User --> Message
    Conversation --> ConversationParticipant
    User --> ConversationParticipant

    Message --> MessageAttachment

    Coach --> Devis
