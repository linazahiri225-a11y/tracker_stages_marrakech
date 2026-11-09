# MarrakechStage

Plateforme Streamlit de recherche d'entreprises et d'opportunités de stage à Marrakech. Le projet combine collecte de données, carte interactive, analyse de CV via OmniRoute, préparation de candidatures, envoi Gmail et suivi.

## Prérequis

- Python 3.10 ou plus récent
- Une clé Google Maps Platform avec Places API activée pour rechercher les entreprises
- OmniRoute lancé et configuré pour les fonctions IA
- Un projet Google Cloud/OAuth configuré si l'envoi Gmail est utilisé

## Installation locale (Windows PowerShell)

```powershell
git clone LIEN_DU_DEPOT
cd tracker_stages_marrakech
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item config.example.py config.py
```

Ouvre ensuite `config.py` et renseigne localement les clés et chemins requis. Ne publie jamais `config.py`, `credentials.json`, `token.json`, les PDF personnels ou les CSV locaux. Ces fichiers sont exclus par `.gitignore`.

Pour Gmail, place le fichier OAuth téléchargé de Google Cloud à l'emplacement configuré. Au premier envoi, autorise l'application depuis le navigateur.

## Lancer l'application

```powershell
streamlit run app.py
```

Streamlit affiche l'adresse locale dans le terminal (généralement `http://localhost:8501`). La collecte des entreprises exige une clé Google Maps valide. Les fonctions IA exigent un OmniRoute accessible à l'adresse configurée.

## Structure du projet

- `app.py` : interface Streamlit et navigation entre les écrans.
- `backend.py` : collecte, normalisation, OmniRoute, Gmail et suivi.
- `analyse_eda.ipynb` : exploration et visualisations exploratoires.
- `README_STRUCTURE.md` : guide des écrans et fonctions du code.
- `config.example.py` : modèle de configuration sans secret.
- `requirements.txt` : dépendances Python.

Google Maps sert à rechercher des entreprises ; les lignes Maps ne sont pas des offres d'emploi. Les sources d'annonces actuellement intégrées sont LinkedIn et le flux RSS Jawb. Leur disponibilité dépend de leur accès réseau et du format renvoyé par les sites.

## Publier sur GitHub

1. Crée un dépôt vide sur GitHub, sans ajouter de README généré par GitHub.
2. Dans le terminal VS Code ouvert dans ce dossier, vérifie les fichiers qui seront versionnés :

   ```powershell
   git status --short
   ```

3. Initialise et envoie le code :

   ```powershell
   git init
   git add .
   git status --short
   git commit -m "Version finale MarrakechStage"
   git branch -M main
   git remote add origin https://github.com/UTILISATEUR/NOM_DU_DEPOT.git
   git push -u origin main
   ```

Remplace l'URL d'exemple par celle du dépôt créé. Avant `git add`, contrôle que les fichiers secrets et personnels ignorés n'apparaissent pas dans `git status`. Après l'envoi, ouvre le dépôt dans une fenêtre privée pour vérifier son accessibilité.
