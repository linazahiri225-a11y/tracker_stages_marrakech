# MarrakechStage — comprendre le code

Ce guide relie les écrans visibles de l’application aux fichiers et fonctions qui les produisent. L’application est écrite en Python avec Streamlit.

## Démarrage

- `app.py` construit l’interface et affiche l’écran sélectionné.
- `backend.py` contient les fonctions de collecte, les appels OmniRoute, l’analyse CV, Gmail et le suivi des candidatures.
- `config.py` fournit les clés et paramètres locaux. **Ne partage pas ce fichier** : il peut contenir des secrets.
- `entreprises_marrakech.csv` contient les données enregistrées par la collecte ; `suivi_candidatures.csv` contient le suivi des candidatures.
- `profil.json`, `mon_cv.pdf` et `ma_lettre_motivation.pdf` stockent les informations et documents du profil.

## Parcours général des données

1. L’application démarre dans `app.py` et charge le profil et le CSV avec `charger_offres()`.
2. `DONNEES` conserve toutes les lignes collectées. `OFFRES` retire les lignes Google Places, car Maps sert aux entreprises et non aux annonces. `ENTS` prépare les entreprises de la carte.
3. Le bouton **Lancer la collecte** appelle `panneau_collecte()` dans `app.py`, puis `backend.executer_collecte_complete()`.
4. Le backend interroge Google Places pour les entreprises et les sources d’annonces configurées. Il normalise et enregistre les résultats dans `entreprises_marrakech.csv`.
5. Streamlit recharge l’écran et affiche les résultats enregistrés.

## Écrans de l’application (`app.py`)

Les sections sont numérotées dans le fichier. La navigation est construite par `NAV` et `goto()` ; la valeur `st.session_state.tab` détermine quel bloc `if/elif` s’affiche.

| Écran | Section / code principal | Résultat visible |
|---|---|---|
| Offres de stage | `if tab == T_OFFRES` (vers ligne 370) | Recherche, filtres par source, liste des annonces, bouton de collecte |
| Carte & entreprises | `elif tab == T_CARTE` (vers ligne 430) | Entreprises Google Maps et carte interactive Folium |
| Mon CV & Lettre | `elif tab == T_CV` (vers ligne 500) | Profil, import et lecture des PDF, texte du CV et de la lettre |
| Analyseur IA | `elif tab == T_ANALYSE` (vers ligne 580) | Analyse du CV et comparaison à une offre via OmniRoute |
| Email & candidature | `elif tab == T_EMAIL` (vers ligne 640) | Brouillon personnalisé, pièces jointes et envoi par Gmail |
| Suivi candidatures | `elif tab == T_SUIVI` (vers ligne 715) | Tableau des candidatures et changement de statut |

Autres fonctions d’interface utiles : `recherche()` filtre les lignes, `dialogue_offre()` affiche le détail d’une annonce, `dialogue_suivi()` affiche une candidature, `badge_source()` dessine le badge de provenance et `pieces_jointes()` liste les PDF prêts à joindre.

## Fonctions importantes (`backend.py`)

| Fonction | Entrée principale | Résultat / effet |
|---|---|---|
| `chercher_places_api()` | Recherche textuelle et clé Google Maps | Liste d’entreprises retournée par Places API |
| `collecter_linkedin()` | Mots-clés et ville | Tableau d’annonces LinkedIn lues par le collecteur existant |
| `collecter_jawb()` | Ville | Tableau d’annonces de stage pertinentes trouvées dans le flux RSS Jawb |
| `executer_collecte_complete()` | Clé Maps et callback de progression | Combine les sources, dédoublonne, écrit le CSV et retourne un DataFrame |
| `nettoyer_donnees()` | DataFrame brut | Ajoute les colonnes attendues et convertit les coordonnées/notes |
| `tester_omniroute()` / `appeler_omniroute()` | Configuration OmniRoute et messages | Vérifie la passerelle ou renvoie le texte généré par le modèle |
| `analyser_cv()` / `calculer_match()` | CV et offre | Renvoie les compétences ou l’analyse de compatibilité IA |
| `generer_email()` | Profil, entreprise, offre et ton | Renvoie un brouillon de candidature produit par OmniRoute |
| `envoyer_email_candidature()` | Destinataire, texte et PDF | Envoie le message avec l’API Gmail après autorisation |
| `charger_suivi()` / `ajouter_suivi()` / `changer_statut_suivi()` | Candidature et statut | Lit ou met à jour le fichier de suivi |

## Où modifier une partie ?

- Texte, boutons, filtres et mise en page : `app.py`, dans le bloc de l’écran concerné.
- Source d’annonces ou format de collecte : fonction source et `executer_collecte_complete()` dans `backend.py`.
- Modèle ou URL OmniRoute : variables lues par `_cfg()` dans `backend.py`, valeurs définies dans `config.py`.
- Envoi Gmail : `gmail_statut()`, `autoriser_gmail()` et `envoyer_email_candidature()` dans `backend.py`.
- Colonnes du CSV : `COLS_OFFRE` dans `app.py` et `COLONNES` dans `backend.py`.

## Lire une fonction

Une fonction `def nom(...):` regroupe une action. Les paramètres entre parenthèses sont ses entrées ; `return` indique ce qu’elle renvoie. Les appels `st.*` affichent les éléments Streamlit. Les appels `backend.nom_fonction(...)` délèguent le traitement au backend. Les blocs `if` et `elif` choisissent le comportement selon l’écran ou les données.

Les nombres de ligne du tableau sont indicatifs : ils changent lorsque le code évolue. Cherche le nom de la section ou de la fonction dans VS Code (`Ctrl+F`).
