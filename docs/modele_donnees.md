# Modèle de données

Ce diagramme représente les principales entités du système ArchiWeb 2026 et leurs relations, en cohérence avec l’expression de besoins du client.

## Description des entités principales

- **Utilisateur** : information de base (id, nom, prénom, email, mot de passe)
- **Coach** : spécialité, téléphone, clients associés
- **Client** : informations personnelles, objectifs sportifs, pathologies, contrats, groupes et tags
- **Séance** : date, durée, type, description, association à un ou plusieurs clients
- **Programme** : nom, description, durée totale, niveau, séances associées
- **Exercice** : nom, catégorie, niveau, consignes
- **Contrat** : type, date début/fin, prix, TVA, paiements associés
- **Paiement** : montant, date, mode
- **Groupe** : nom, clients associés
- **Tag** : nom, clients associés
- **Message** : contenu, expéditeur, destinataire(s), date

## Diagramme de classes
```mermaid
classDiagram
    class Utilisateur {
        +id: int
        +nom: string
        +prenom: string
        +email: string
        +mot_de_passe: string
        +role: string
    }

    class Coach {
        +specialite: string
        +telephone: string
    }

    class Client {
        +nom: string
        +prenom: string
        +email: string
        +telephone: string
        +date_naissance: date
        +taille: int
        +poids: float
        +objectifs_sportifs: string
        +pathologies_blessures: string
        +consentement_rgpd: bool
        +est_archive: bool
        +date_creation: datetime
    }

    class Salle {
        +nom: string
        +adresse: string
        +telephone: string
    }

    class Seance {
        +date: date
        +duree: int
        +type: string
        +description: string
        +capacite_max: int
    }

    class Programme {
        +nom: string
        +description: string
        +duree_total: int
        +niveau: string
        +payant: bool
    }

    class Exercice {
        +nom: string
        +categorie: string
        +niveau: string
        +consignes: string
    }

    class Offre {
        +nom: string
        +type: string
        +prix: float
        +tva: float
    }

    class Contrat {
        +type: string
        +date_debut: date
        +date_fin: date
        +prix_total: float
        +statut: string
    }

    class Facture {
        +numero: string
        +date_emission: date
        +montant_total: float
        +statut: string
    }

    class Paiement {
        +montant: float
        +date: date
        +mode: string
    }

    class Message {
        +contenu: string
        +date_envoi: datetime
        +lu: bool
    }

    class Groupe {
        +nom: string
    }

    class Tag {
        +nom: string
    }

    %% Héritage
    Utilisateur <|-- Coach
    Utilisateur <|-- Client

    %% Relations métier
    Coach "1" -- "0..*" Client : gère
    Coach "1" -- "0..*" Seance : planifie
    Coach "0..*" -- "0..*" Salle : intervient_dans

    Client "0..*" -- "0..*" Seance : participe
    Seance "1" -- "0..*" Exercice : contient
    Programme "1" -- "0..*" Seance : inclut

    Offre "1" -- "0..*" Contrat : definit
    Client "1" -- "0..*" Contrat : possède

    Contrat "1" -- "0..*" Facture : genere
    Facture "1" -- "1..*" Paiement : reglee_par

    Client "0..*" -- "0..*" Groupe : appartient
    Client "0..*" -- "0..*" Tag : etiquete

    Utilisateur "1" -- "0..*" Message : envoie
    Utilisateur "1" -- "0..*" Message : recoit
```