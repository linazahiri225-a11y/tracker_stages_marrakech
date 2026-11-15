# MarrakechStage

Plateforme Streamlit de recherche d'entreprises et d'opportunités de stage à Marrakech. Le projet combine collecte de données, carte interactive, analyse de CV via OmniRoute, préparation de candidatures, envoi Gmail et suivi.

## Prérequis

- Python 3.10 ou plus récent
- Une clé Google Maps Platform avec Places API activée pour rechercher les entreprises
- Une clé Gemini (quota gratuit) ou une URL OmniRoute accessible depuis le serveur pour les fonctions IA
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

Pour utiliser Gmail en local, active Gmail API dans Google Cloud, télécharge un client OAuth de type « Application de bureau » sous `credentials.json`, lance l'application puis clique sur « Connecter Gmail ». Google crée alors `token.json` après votre autorisation. Ne versionnez ni `credentials.json` ni `token.json`.

### Gmail sur Streamlit Community Cloud

Le fichier `credentials.json` est volontairement exclu de Git : sa simple présence sur votre ordinateur ne le rend pas disponible dans le conteneur Cloud. Pour envoyer depuis l'application déployée :

1. Autorisez Gmail une fois en local avec le bouton « Connecter Gmail » ci-dessus.
2. Ouvrez `token.json` localement et copiez tout son contenu JSON.
3. Dans Streamlit, ouvrez **Manage app > Settings > Secrets**, puis ajoutez ce secret en remplaçant le texte d'exemple par le contenu complet du fichier :

   ```toml
   GMAIL_TOKEN_JSON = '''COLLER_ICI_LE_CONTENU_COMPLET_DE_token.json'''
   ```

4. Enregistrez les Secrets et attendez le redémarrage de l'application. Ne collez jamais le jeton dans GitHub ou dans le code.

Si l'écran OAuth Google est en mode **Testing**, le jeton de rafraîchissement peut expirer après 7 jours. Google documente cette limite ; pour un accès durable, vérifiez les exigences de publication de l'écran OAuth. Les annonces d'emploi ne publient pas toujours l'adresse du recruteur : l'application ne fabrique plus d'adresses e-mail. Elle cherche uniquement les adresses présentes sur les sites publics des entreprises, et vous pouvez ouvrir l'annonce puis saisir manuellement un contact.

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

### Déploiement gratuit de l'analyse IA

Pour éviter l'hébergement OmniRoute payant, l'application peut appeler directement Gemini avec une clé API. Créez une clé dans [Google AI Studio](https://aistudio.google.com/apikey), puis, dans Streamlit Community Cloud, ouvrez l'application, choisissez **Manage app > ⋮ > Settings > Secrets**, et ajoutez :

```toml
GEMINI_API_KEY = "votre-cle-api-gemini"
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"
```

Enregistrez les secrets, puis attendez le redémarrage de l'application et relancez l'analyse. En cas d'erreur 503 (surcharge temporaire), l'application réessaie une fois puis bascule sur `GEMINI_FALLBACK_MODEL`. Gemini propose un niveau gratuit soumis à des limites d'utilisation susceptibles de changer ; consultez les [tarifs et limites actuels](https://ai.google.dev/gemini-api/docs/pricing). Le niveau gratuit indique que les contenus envoyés peuvent être utilisés pour améliorer les produits Google : évitez d'envoyer des informations confidentielles ou personnelles dans le CV. Les secrets Streamlit et variables d'environnement sont prioritaires sur `config.py` local. Ne mettez aucune clé réelle dans GitHub.

L'appel Gemini est utilisé dès que `GEMINI_API_KEY` est défini ; sinon, l'application essaie la configuration OmniRoute habituelle.

Les PDF, profils et fichiers CSV locaux sont exclus de Git. Ils ne sont donc pas automatiquement présents après déploiement ; ajoutez une gestion de données adaptée si l'application doit retrouver les mêmes fichiers en production.

Les annonces affichées ciblent les stages/PFE data, IA et métiers IT à Marrakech : Data Analyst, Data Science, Power BI/BI, machine learning, développement web/logiciel, cybersécurité, réseaux et cloud. Une simple mention de l'IA dans une annonce marketing ne suffit pas à la faire apparaître. Les offres sont recherchées sur PostulerCV, Stagiaires.ma, le flux RSS Jawb (flux général de Marrakech et filtres métier) et LinkedIn, avec plusieurs mots-clés par source. Les pages des sources ne garantissent pas une API stable ; vérifiez chaque annonce sur son lien d'origine. Google Maps sert uniquement à rechercher des entreprises, pas à créer des offres.

Les sites de recrutement intégrés sont des sources publiques gratuites, pas des bases « open source » au sens de données sous licence ouverte. Leur disponibilité dépend de l'accès et du format de chaque site.

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
