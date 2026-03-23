# Portail CBM - Guide Utilisateur

**Module:** Portail du Personnel Clinique (clinic_staff_portal)
**Version:** 16.0.3.3.0
**Derniere mise a jour:** Fevrier 2026

---

## Table des matieres

1. [Connexion et ecran d'accueil](#1-connexion-et-ecran-daccueil)
2. [Consommation patient (facturable)](#2-consommation-patient-facturable)
3. [Demande de produits (pharmacie)](#3-demande-de-produits-pharmacie)
4. [Consommation interne / departement](#4-consommation-interne--departement)
5. [Retour de produits](#5-retour-de-produits)
6. [Historique (Suivi)](#6-historique-suivi)
7. [Caisse (Cashier)](#7-caisse-cashier)
8. [Achats (Bons de commande)](#8-achats-bons-de-commande)
9. [Autres tuiles](#9-autres-tuiles)
10. [Questions frequentes](#10-questions-frequentes)

---

## 1. Connexion et ecran d'accueil

### Acces
Le portail CBM se lance automatiquement a l'ouverture d'Odoo. L'interface est en mode plein ecran — pas de menus Odoo visibles.

### Ecran d'accueil
L'ecran principal affiche des **tuiles** (carres colores). Chaque tuile represente une action :

| Tuile | Description |
|-------|-------------|
| Consommation Patient | Dispenser des medicaments a un patient (facture) |
| Demande Pharmacie | Commander des produits depuis la pharmacie |
| Consommation Interne | Utiliser des produits sans facturation |
| Retour | Retourner des produits au stock |
| **Caisse** | Poste d'encaissement : validation devis, paiements, remboursements |
| **Achats** | Bons de commande fournisseur, reception, correction |
| Devis | Voir les devis en cours |
| Factures | Voir les factures |
| Maintenance | Signaler une panne |
| Conge | Demander un jour de conge |
| Messages | Ouvrir la messagerie interne |

Les tuiles visibles dependent de votre role et de votre emplacement.

### Mode sombre / clair
Le bouton en haut a droite permet de basculer entre le mode sombre et le mode clair.

---

## 2. Consommation patient (facturable)

C'est l'operation principale pour le personnel infirmier. Elle cree un transfert de stock ET une ligne de facturation sur le bon de commande (devis) du patient.

### Etape 1 : Selectionner le type d'operation
Cliquez sur la tuile correspondante (ex: "Hospitalisation", "Urgence").

### Etape 2 : Selectionner le patient
- **Recherche par nom** : Tapez le nom du patient dans la barre de recherche
- **Recherche par code-barres** : Scannez le bracelet du patient

Le systeme charge automatiquement le devis existant du patient s'il en a un.

### Etape 3 : Ajouter des produits
Trois methodes :

1. **Recherche** : Tapez le nom du produit dans la barre de recherche
2. **Code-barres** : Scannez le code-barres du produit
3. **Selection rapide** : Cliquez sur un produit dans la grille "Quick Pick" (si configuree pour votre emplacement)

Pour chaque produit :
- La quantite par defaut est 1
- Utilisez les boutons **+** et **-** pour ajuster
- Le stock disponible est affiche a cote du produit

### Etape 4 : Modifier des produits existants
Si le patient a deja un devis avec des produits :
- Les produits existants sont affiches avec leur quantite actuelle
- Vous pouvez **augmenter** la quantite (consommation supplementaire)
- Vous pouvez **reduire** la quantite (retour partiel)
- Vous pouvez **supprimer** un produit completement (retour total)

### Etape 5 : Confirmer
Cliquez sur **"Confirmer la dispensation"**.

#### Si vous avez reduit ou supprime des produits :
Un message de confirmation apparait :

> **Suppression de produits**
> Patient : Nom du Patient
>
> | Produit | Avant | Apres | Supprime |
> |---------|-------|-------|----------|
> | Omeprazole 20mg | 6 | 4 | -2 |
> | Paracetamol INJ | 3 | 0 | -3 |

- **Revenir** : Annuler et modifier les quantites
- **Confirmer la suppression** : Les produits sont retournes au stock

**Important** : La suppression est enregistree dans le journal de tracabilite. Chaque retour est associe au lot exact qui avait ete consomme.

### Ce qui se passe en arriere-plan :
1. Un transfert de **retour** est cree et valide (les produits reviennent au stock)
2. Un transfert de **consommation** est cree et valide (les nouveaux produits sortent du stock)
3. Le devis du patient est mis a jour avec les quantites et lots corrects
4. Le journal de consommation (ledger) est mis a jour

### Cas particuliers :
- **Stock insuffisant** : Le produit est ignore et une alerte de stock est creee automatiquement. Les autres produits sont consommes normalement.
- **Lot multiple** : Si un produit est consomme sur plusieurs lots (FEFO), le devis aura une ligne par lot.

---

## 3. Demande de produits (pharmacie)

Utilisez cette fonction pour commander des produits depuis la pharmacie centrale vers votre emplacement (service, bloc, etc.).

### Etape 1 : Selectionner la tuile de demande
Cliquez sur la tuile correspondante a votre service.

### Etape 2 : Ajouter des produits
Recherchez et ajoutez les produits necessaires avec les quantites souhaitees.

### Etape 3 : Soumettre
Cliquez sur **"Valider la demande"**.

### Apres soumission :
- La demande apparait dans la liste des transferts en attente
- Les responsables de la pharmacie sont notifies
- Le statut passe de "Brouillon" a "En attente" puis "Fait" une fois valide par la pharmacie

### Limites :
- Si vous avez trop de demandes en attente (seuil configure par l'administration), vous ne pourrez pas en creer de nouvelles
- Un message vous indiquera combien de demandes sont en attente

---

## 4. Consommation interne / departement

Pour les consommations non facturables (produits utilises par le service sans patient specifique).

### Consommation departement :
1. Selectionnez la tuile de consommation departement
2. Choisissez le departement destinataire
3. Ajoutez les produits
4. Confirmez

### Consommation interne :
1. Selectionnez la tuile de consommation interne
2. Ajoutez les produits directement
3. Confirmez

**Aucune facturation n'est generee** pour ces types de consommation.

---

## 5. Retour de produits

Pour retourner des produits a la pharmacie (produits non utilises, erreur de dispensation, etc.).

1. Selectionnez la tuile de retour
2. Recherchez les produits a retourner
3. Indiquez les quantites
4. Confirmez

Le systeme utilise le **lot exact** qui avait ete consomme (methode LIFO : dernier entre, premier sorti).

---

## 6. Historique (Suivi)

L'ecran "Suivi" affiche vos operations recentes :

| Colonne | Description |
|---------|-------------|
| Reference | Numero du transfert (ex: HOSPIT-OUT00816) |
| Patient | Nom du patient (si applicable) |
| Type | Consommation, Demande, Retour |
| Date | Date et heure de la soumission |
| Statut | Brouillon, En attente, Fait, Annule |

Cliquez sur une ligne pour voir le detail complet (produits, quantites, lots).

---

## 7. Caisse (Cashier)

La caisse est le poste de travail pour le personnel habilite a encaisser les paiements patients. L'interface affiche les documents sous forme de **cartes colorees** selon leur statut.

### Systeme de cartes colorees

| Couleur | Signification | Actions possibles |
|---------|---------------|-------------------|
| **Bleue** | Devis (brouillon) | Valider et encaisser |
| **Orange** | Facture impayee | Encaisser le paiement |
| **Verte** | Facture payee | Imprimer recu, rembourser |
| **Rouge** | Facture annulee/reversee | Consulter l'historique |

### 7.1. Ouvrir une session

1. Cliquez sur la tuile **"Caisse"** sur l'ecran d'accueil
2. Le systeme ouvre automatiquement une nouvelle session, ou reprend la session du jour si elle existe deja
3. L'en-tete affiche le total courant et le nombre de transactions

> **Note :** Une seule session peut etre ouverte par utilisateur. Les sessions de la veille sont fermees automatiquement.

### 7.2. Rechercher un document

- **Vue par defaut :** Affiche les devis et factures du jour
- **Recherche :** Tapez le nom du patient, le numero de devis ou la reference dans la barre de recherche
- Les resultats apparaissent sous forme de cartes colorees dans la liste

### 7.3. Valider un devis (carte bleue)

C'est l'operation principale : transformer un devis patient en facture payee.

#### Sans convention :
1. Selectionnez une carte bleue (devis)
2. Verifiez les lignes de produits dans le panneau de detail
3. Choisissez la methode de paiement : **Especes**, **Carte** ou **Cheque**
4. Cliquez sur **"Valider et Encaisser"**

#### Avec convention (CNAS, CASNOS, Mutuelle) :
1. Selectionnez une carte bleue (devis)
2. Activez le bouton **"Avec Convention"**
3. Choisissez la convention dans la liste deroulante
4. Le systeme calcule automatiquement la repartition :

| | Exemple |
|--|---------|
| Montant total | 10 000 DA |
| Couverture convention (70%) | 7 000 DA |
| **Part patient** | **3 000 DA** |

5. Choisissez la methode de paiement
6. Cliquez sur **"Valider et Encaisser"**

Le systeme cree deux factures : une pour le patient (part patient) et une pour la convention (part assurance).

### 7.4. Encaisser une facture impayee (carte orange)

Pour les factures deja creees mais pas encore payees :

1. Selectionnez une carte orange
2. Le solde restant est affiche
3. Entrez le montant a encaisser (peut etre partiel)
4. Choisissez la methode de paiement
5. Cliquez sur **"Encaisser"**

> **Paiement partiel :** Si le montant entre est inferieur au total, la facture reste en statut "impayee" avec le solde restant. Un avertissement s'affiche avec le reste a payer.

### 7.5. Annuler une facture

Pour annuler completement une facture payee :

1. Selectionnez une carte verte (facture payee)
2. Cliquez sur **"Annuler"**
3. Confirmez l'annulation

Le systeme cree un avoir (note de credit) et reverse le paiement. La carte passe en rouge.

> **Annulation rapide :** Immediatement apres un encaissement, un bouton **"Annuler"** apparait pendant 5 secondes dans une notification. Cliquez dessus pour annuler instantanement sans ouvrir le detail.

### 7.6. Rembourser (partiellement ou totalement)

Trois modes de remboursement sont disponibles depuis une carte verte :

#### Remboursement total
Le patient est rembourse integralement. La facture est reversee.

#### Remboursement partiel
1. Entrez le montant a rembourser (inferieur au total)
2. Le systeme cree une facture de remboursement pour ce montant
3. La facture originale reste ouverte pour le solde

#### Remboursement partiel avec cloture
1. Entrez le montant a rembourser
2. Indiquez le motif
3. Le systeme rembourse le montant indique et passe le reste en perte (ecart autorise)
4. La facture est completement cloturee

### 7.7. Imprimer un recu

Apres chaque paiement reussi (carte verte) :
1. Cliquez sur **"Imprimer Recu"**
2. Le recu s'imprime automatiquement sur l'imprimante par defaut (impression silencieuse)

Le recu contient : numero de facture, date, patient, lignes de produits, totaux, methode de paiement, nom du caissier, et informations de convention si applicable.

### 7.8. Fermer la session et Rapport Z

En fin de journee :

1. Cliquez sur **"Fermer Session"** dans le panneau de session
2. Le rapport Z s'affiche avec le resume :

| Rubrique | Montant |
|----------|---------|
| Especes | 12 500 DA |
| Carte | 8 300 DA |
| Cheque | 3 200 DA |
| **Total attendu** | **24 000 DA** |

3. Comptez votre caisse physique
4. Entrez le montant compte dans le champ prevu
5. Le systeme calcule l'ecart :
   - **Positif** = excedent de caisse
   - **Negatif** = deficit de caisse
6. Cliquez sur **"Cloturer"** pour fermer definitivement la session

### 7.9. Methodes de paiement

| Methode | Utilisation |
|---------|-------------|
| **Especes** | Paiement en liquide. Comptabilise dans le journal de caisse |
| **Carte** | Paiement par carte bancaire. Comptabilise dans le journal bancaire |
| **Cheque** | Paiement par cheque. Comptabilise dans le journal bancaire |

---

## 8. Achats (Bons de commande)

Le module d'achats permet au personnel de reception/magasin de creer, suivre et recevoir des bons de commande fournisseur directement depuis le portail.

> **Acces :** Cette fonctionnalite est visible uniquement pour les utilisateurs ayant un type d'operation de reception (entree de stock).

### 8.1. Tableau de bord des achats

Cliquez sur la tuile **"Achats"** pour acceder au tableau de bord. En haut, trois compteurs affichent :

| Compteur | Signification |
|----------|---------------|
| **Brouillons** | Bons de commande en cours de redaction |
| **A approuver** | Bons de commande en attente de validation hierarchique |
| **A recevoir** | Bons de commande approuves, prets pour reception |

#### Filtres disponibles :
- **Par statut :** Tous, Brouillon, A approuver, Confirme, Annule, A recevoir
- **Par recherche :** Numero de BC, nom du fournisseur ou reference
- **Par date :** Periode de creation (date de debut / date de fin)

### 8.2. Creer un bon de commande

#### Etape 1 : Selectionner le fournisseur
- Tapez le nom du fournisseur dans la barre de recherche (minimum 2 caracteres)
- Selectionnez-le dans la liste
- **Nouveau fournisseur ?** Le systeme peut creer un fournisseur a la volee si le nom n'existe pas

#### Etape 2 : Ajouter la reference fournisseur (facultatif)
Entrez la reference de la facture ou du bon de livraison fournisseur. Cette reference doit etre unique par fournisseur.

#### Etape 3 : Ajouter des produits
Pour chaque ligne :
1. Recherchez le produit par nom ou code
2. **Nouveau produit ?** Le systeme peut creer un produit a la volee
3. Indiquez la **quantite**
4. L'**unite de mesure** est pre-remplie (modifiable parmi les unites compatibles)
5. Le **prix unitaire** est pre-rempli depuis le tarif fournisseur (modifiable)
6. Selectionnez la **taxe** applicable si necessaire

#### Etape 4 : Soumettre

Deux options :

| Action | Description |
|--------|-------------|
| **Enregistrer en brouillon** | Sauvegarde le BC sans l'envoyer pour approbation. Vous pouvez le modifier plus tard. |
| **Soumettre pour approbation** | Envoie le BC dans le circuit de validation. Selon le montant, une approbation hierarchique peut etre requise. |

### 8.3. Modifier un bon de commande (brouillon uniquement)

Depuis le tableau de bord, cliquez sur un BC en statut **Brouillon** pour l'ouvrir en edition :

- **Changer le fournisseur**
- **Ajouter** ou **supprimer** des lignes de produits
- **Modifier** les quantites, prix ou taxes
- **Valider** (envoyer pour approbation)
- **Supprimer** le BC completement

> **Attention :** Les BC confirmes ou approuves ne sont plus modifiables depuis le portail.

### 8.4. Circuit d'approbation

Apres soumission, le BC passe dans un circuit d'approbation qui depend du montant total :

- **Sous le seuil :** Le BC est approuve automatiquement (statut "Confirme")
- **Au-dessus du seuil :** Le BC passe en statut **"A approuver"** et attend la validation d'un responsable

Un badge dans la barre laterale indique le nombre de BC en attente d'approbation.

### 8.5. Recevoir une commande

Quand un BC est approuve (statut "Confirme"), une reception est creee automatiquement.

#### Etape 1 : Acceder a la reception
- Depuis le tableau de bord, filtrez par **"A recevoir"**
- Cliquez sur **"Recevoir"** a cote du BC concerne

#### Etape 2 : Renseigner les lignes recues
Pour chaque produit :

| Champ | Description |
|-------|-------------|
| **Quantite recue** | Nombre d'unites effectivement recues (peut differer de la commande) |
| **Numero de lot** | Obligatoire pour les produits traces. Entrez le numero du lot du fournisseur |
| **Date d'expiration** | Date limite du lot (minimum 30 jours a partir d'aujourd'hui) |
| **Prix unitaire** | Modifiable si le prix reel differe du prix commande |

> **Astuce :** Cliquez sur **"Generer les lots"** pour creer automatiquement des lots avec des numeros standardises et une date d'expiration par defaut (3 ans).

#### Etape 3 : Valider la reception
Cliquez sur **"Valider la reception"**.

Le systeme :
1. Cree ou recherche les lots avec les numeros et dates indiques
2. Enregistre les quantites recues
3. Genere automatiquement une **facture fournisseur** (bon a payer)
4. Genere un **PDF** de la facture en piece jointe

> **Reception partielle :** Si les quantites recues sont inferieures aux quantites commandees, un reliquat est cree automatiquement pour les unites manquantes.

### 8.6. Corriger une reception

Si une erreur est constatee apres validation (mauvaise quantite, mauvais lot, mauvais prix) :

1. Ouvrez la reception validee depuis le tableau de bord
2. Cliquez sur **"Correction"**
3. Modifiez les champs necessaires :
   - **Quantite en moins** : Un retour fournisseur est cree automatiquement
   - **Quantite en plus** : Une reception supplementaire est creee automatiquement
   - **Changement de lot** : L'ancien lot est retourne et le nouveau est recu
4. Confirmez la correction

Toutes les corrections sont tracees dans l'historique du BC avec le nom de l'utilisateur.

### 8.7. Telecharger la facture fournisseur

Depuis un BC recu, cliquez sur **"Telecharger PDF"** pour obtenir la facture fournisseur au format PDF.

### 8.8. Restriction de creation (anti-accumulation)

Si votre emplacement a des receptions en retard (non traitees depuis X jours, seuil configure par l'administration), la creation de nouveaux BC sera bloquee. Un message vous indiquera :
- Le nombre de receptions en attente
- Le delai depasse
- Le responsable a contacter

---

## 9. Autres tuiles

### Maintenance
Signalez une panne d'equipement :
1. Selectionnez l'equipement concerne
2. Decrivez le probleme
3. Soumettez — l'equipe technique est notifiee

### Conge
Soumettez une demande de conge directement depuis le portail.

### Documents
Accedez aux procedures, guides et formations publies par l'administration.

### Messages
Ouvrez la messagerie interne Odoo pour communiquer avec vos collegues.

---

## 10. Questions frequentes

### Consommation

**Q : Le bouton "Confirmer" est grise, pourquoi ?**
R : Soit aucun produit n'est selectionne, soit vous avez trop de transferts en attente. Verifiez votre historique.

**Q : J'ai un message "Stock insuffisant", que faire ?**
R : Le produit n'est pas disponible dans votre emplacement. Contactez la pharmacie pour un reapprovisionnement. Le systeme a cree une alerte automatiquement.

**Q : Je me suis trompe de quantite, comment corriger ?**
R : Rechargez la page du patient. Les quantites actuelles sont affichees. Modifiez la quantite et resoumettez. Le systeme calculera automatiquement les retours necessaires.

**Q : Puis-je annuler une consommation deja validee ?**
R : Non, les consommations validees ne peuvent pas etre annulees depuis le portail. Contactez votre responsable ou l'administration.

**Q : Le patient n'apparait pas dans la recherche ?**
R : Verifiez l'orthographe. Le patient doit etre enregistre dans le systeme Bahmni/OpenMRS au prealable.

### Caisse

**Q : J'ai plusieurs sessions de caisse ouvertes ?**
R : Le systeme ferme automatiquement les sessions de la veille. Si une session du jour est restee ouverte, elle sera reprise automatiquement.

**Q : Comment appliquer une convention sur un devis ?**
R : Selectionnez le devis (carte bleue), activez le bouton "Avec Convention", puis choisissez la convention dans la liste. La repartition patient/convention se calcule automatiquement.

**Q : Puis-je annuler un paiement que je viens d'effectuer ?**
R : Oui, immediatement apres le paiement, un bouton "Annuler" apparait pendant 5 secondes dans la notification. Passe ce delai, utilisez la fonction de remboursement depuis la carte verte.

**Q : Quelle est la difference entre "remboursement partiel" et "remboursement partiel avec cloture" ?**
R : Le remboursement partiel rembourse un montant et laisse la facture ouverte pour le solde. Le remboursement avec cloture rembourse un montant et passe le reste en perte (utile pour les cas litigieux).

**Q : Le rapport Z ne correspond pas a ma caisse physique ?**
R : Entrez le montant physiquement compte. L'ecart est enregistre et visible par l'administration. Les ecarts recurrents doivent etre signales a votre responsable.

### Achats

**Q : Je ne peux pas creer de bon de commande, un message de blocage s'affiche ?**
R : Votre emplacement a des receptions en retard. Traitez les receptions en attente avant de creer de nouveaux BC. Contactez votre responsable si le probleme persiste.

**Q : Mon bon de commande est "A approuver" depuis longtemps ?**
R : Le BC attend la validation d'un responsable. Le badge dans la barre laterale indique le nombre de BC en attente. Contactez le responsable designe pour accelerer l'approbation.

**Q : Je me suis trompe dans la reception (mauvaise quantite ou mauvais lot) ?**
R : Ouvrez la reception validee et cliquez sur "Correction". Modifiez les champs necessaires. Le systeme creera automatiquement les retours et receptions de correction.

**Q : La date d'expiration est refusee a la reception ?**
R : La date d'expiration doit etre au minimum 30 jours dans le futur. Les produits dont la date est trop proche ne peuvent pas etre receptionnees via le portail.

### General

**Q : Comment changer le mode sombre/clair ?**
R : Cliquez sur l'icone de theme en haut a droite de l'ecran d'accueil. Le choix est sauvegarde localement.

---

*Document genere a partir du code source v16.0.3.3.0 — Fevrier 2026*