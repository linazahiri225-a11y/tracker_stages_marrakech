"""
backend.py - KechTech Stages
Collecte des entreprises / offres à Marrakech, génération de lettres et
scoring de compatibilité via OmniRoute (passerelle IA compatible OpenAI),
envoi d'e-mails de candidature et suivi.

Variables d'environnement (optionnelles) :
    OMNIROUTE_BASE_URL  ex: http://localhost:20128/v1
    OMNIROUTE_API_KEY   clé générée dans le dashboard OmniRoute
    OMNIROUTE_MODEL     nom du modèle ou du "combo" configuré dans OmniRoute
"""
import base64
import json
import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
import random
import re
import sys
import urllib.parse
import urllib.request
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
API_URL = "https://places.googleapis.com/v1/places:searchText"
CSV_ENTREPRISES = "entreprises_marrakech.csv"
CSV_SUIVI = "suivi_candidatures.csv"

try:
    import config
except ImportError:  # config.py absent : on retombe sur les variables d'environnement
    config = None


def _cfg(nom, defaut=""):
    # En local, les valeurs viennent de config.py ou des variables d'environnement.
    valeur = getattr(config, nom, None) or os.getenv(nom)
    if valeur:
        return valeur
    # Sur Streamlit Community Cloud, les secrets se configurent dans
    # Manage app > Settings > Secrets, pas dans config.example.py.
    try:
        import streamlit as st
        valeur = st.secrets.get(nom)
        if valeur:
            return str(valeur)
    except Exception:
        # Streamlit peut être absent ou ses secrets non configurés en local.
        pass
    return defaut


GOOGLE_MAPS_API_KEY = _cfg("GOOGLE_MAPS_API_KEY")

OMNIROUTE = {
    "base_url": _cfg("OMNIROUTE_BASE_URL", "http://localhost:20128/v1"),
    "api_key": _cfg("OMNIROUTE_API_KEY"),
    "model": _cfg("OMNIROUTE_MODEL", "auto"),
}

PROFIL = {
    "nom": "Lina Zahiri",
    "titre": "IA Data Analyst",
    "competences": [
        "python", "pandas", "numpy", "scikit-learn", "sql", "power bi", "dax",
        "machine learning", "etl", "postgresql", "streamlit", "fastapi",
    ],
}

DEFAULT_QUERIES = [
    "entreprise informatique Marrakech",
    "agence web Marrakech",
    "intelligence artificielle data Marrakech",
    "cabinet conseil IT Marrakech",
    "société de services informatiques SSII Marrakech",
]

# Modèles de postes utilisés pour COMPLÉTER les champs manquants (estimations).
POSTES_VARIATION = [
    {
        "titre": "Stage Ingénieur IA & Machine Learning (Computer Vision / NLP)",
        "domaine": "IA & Machine Learning",
        "remuneration": "4 000 - 5 500 MAD / mois",
        "duree": "6 mois (possibilité de pré-embauche)",
        "competences": "Python, PyTorch, FastAPI, Gemini API, Docker, RAG, Vector DB",
        "description": "Rejoignez un laboratoire R&D spécialisé dans les solutions d'IA générative et de vision par ordinateur pour le tourisme et le smart hospitality à Marrakech.",
        "missions": "Développement de pipelines RAG pour assistants virtuels\nEntraînement et fine-tuning de modèles de vision par ordinateur\nIntégration d'APIs LLM dans des microservices FastAPI",
        "profil": "Élève ingénieur en Master 2 / 3ème année (Data Science, IA)\nSolide expérience en Python et Deep Learning\nSens de l'innovation et rigueur scientifique",
    },
    {
        "titre": "Stage PFE - Data Analyst & Business Intelligence (Power BI / Python)",
        "domaine": "Data Analyst & BI",
        "remuneration": "3 500 - 4 500 MAD / mois",
        "duree": "5 à 6 mois",
        "competences": "Python, SQL, Power BI, DAX, ETL, Pandas, PostgreSQL",
        "description": "Conception de dashboards décisionnels et traitement de pipelines de données clients pour le retail et l'hôtellerie de luxe.",
        "missions": "Modélisation de données et création de datamarts\nAutomatisation de flux ETL via Python et SQL\nCréation de rapports interactifs et KPIs sur Power BI",
        "profil": "Étudiant(e) en Master ou école d'ingénieurs (Informatique, Big Data)\nMaîtrise de SQL, Python et Power BI",
    },
    {
        "titre": "Stage Data Engineer & Big Data (Pipelines Cloud & Lakehouse)",
        "domaine": "Data Engineering & Big Data",
        "remuneration": "4 500 - 6 000 MAD / mois",
        "duree": "6 mois",
        "competences": "Python, PySpark, Snowflake, Airflow, SQL, AWS, Docker",
        "description": "Conception d'entrepôts de données modernes et de pipelines cloud automatisés pour l'analytique volumineuse.",
        "missions": "Construction de DAGs Airflow pour l'ingestion quotidienne\nOptimisation de requêtes PySpark et Snowflake\nMise en place d'architectures Lakehouse sécurisées",
        "profil": "Formation en ingénierie des données / Cloud Computing\nBases solides en bases de données distribuées et Linux",
    },
    {
        "titre": "Stage Développeur Full-Stack Python / React (Applications Data-Driven)",
        "domaine": "Développement Full-Stack",
        "remuneration": "3 500 - 5 000 MAD / mois",
        "duree": "6 mois",
        "competences": "Python, Django, FastAPI, React.js, TypeScript, PostgreSQL, Git",
        "description": "Développement d'interfaces analytiques et de backends robustes pour des plateformes SaaS.",
        "missions": "Conception d'APIs REST avec FastAPI / Django\nDéveloppement d'interfaces React.js\nIntégration de graphiques décisionnels interactifs",
        "profil": "Étudiant(e) en génie logiciel / full-stack\nMaîtrise de JavaScript/TypeScript et Python",
    },
]

QUARTIERS = ["Guéliz", "Hivernage", "Sidi Ghanem", "Daoudiate"]

COLONNES = [
    "place_id", "nom", "titre_offre", "adresse", "telephone", "email_contact",
    "email_verifie", "site_web", "note", "nombre_avis", "latitude", "longitude",
    "categorie", "source", "domaine", "quartier", "type_stage", "remuneration",
    "duree", "description", "competences", "missions", "profil_requis",
    "date_publication",
]


# ------------------------------------------------------------------
# OMNIROUTE (passerelle IA compatible OpenAI)
# ------------------------------------------------------------------
def configurer_omniroute(base_url=None, api_key=None, model=None):
    if base_url:
        OMNIROUTE["base_url"] = base_url.rstrip("/")
    if api_key is not None:
        OMNIROUTE["api_key"] = api_key
    if model:
        OMNIROUTE["model"] = model


def _entetes_omniroute():
    h = {"Content-Type": "application/json"}
    if OMNIROUTE["api_key"]:
        h["Authorization"] = f"Bearer {OMNIROUTE['api_key']}"
    return h


def omniroute_disponible():
    """La clé est facultative : OmniRoute peut tourner sans clé en local (REQUIRE_API_KEY désactivé)."""
    return bool(OMNIROUTE["base_url"])


def tester_omniroute(timeout=4):
    """Retourne (ok, message) en interrogeant GET /models."""
    try:
        r = requests.get(f"{OMNIROUTE['base_url'].rstrip('/')}/models", headers=_entetes_omniroute(), timeout=timeout)
    except Exception as e:
        return False, f"OmniRoute injoignable à {OMNIROUTE['base_url']} ({str(e)[:90]}). Est-il lancé ?"
    if r.status_code == 200:
        return True, "Connexion OK : OmniRoute répond."
    if r.status_code in (401, 403):
        return False, "OmniRoute répond mais refuse la clé : créez une clé d'endpoint dans son dashboard."
    return False, f"OmniRoute a répondu HTTP {r.status_code}."


def appeler_omniroute(messages, temperature=0.4, max_tokens=700, timeout=40):
    """Appelle /chat/completions d'OmniRoute. Retourne le texte ou None."""
    if not omniroute_disponible():
        return None
    url = f"{OMNIROUTE['base_url'].rstrip('/')}/chat/completions"
    headers = _entetes_omniroute()
    payload = {
        "model": OMNIROUTE["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if res.status_code == 200:
            texte = res.json()["choices"][0]["message"]["content"].strip()
            if texte:
                DERNIERE_ERREUR.pop("omniroute", None)
                return texte
            DERNIERE_ERREUR["omniroute"] = (
                "OmniRoute n'a renvoyé aucun texte. Vérifiez dans son tableau de bord > Providers "
                "qu'au moins un fournisseur IA est connecté et actif, puis réessayez : "
                "http://localhost:20128/dashboard/providers"
            )
        elif res.status_code in (401, 403):
            DERNIERE_ERREUR["omniroute"] = ("OmniRoute refuse la clé (HTTP %d) : utilisez une clé d'endpoint créée dans le "
                                            "dashboard d'OmniRoute, pas une clé Google/Gemini." % res.status_code)
        else:
            DERNIERE_ERREUR["omniroute"] = f"OmniRoute a répondu HTTP {res.status_code} : {res.text[:150]}"
    except requests.exceptions.ConnectionError:
        DERNIERE_ERREUR["omniroute"] = f"OmniRoute est injoignable à {OMNIROUTE['base_url']} : est-il lancé (commande « omniroute ») ?"
    except Exception as e:
        DERNIERE_ERREUR["omniroute"] = f"Erreur OmniRoute : {str(e)[:150]}"
    print(DERNIERE_ERREUR.get("omniroute"))
    return None


class ErreurOmniRoute(RuntimeError):
    """Une opération qui dépend de l'IA n'a pas pu être terminée."""


def _exiger_texte_omniroute(messages, **kwargs):
    texte = appeler_omniroute(messages, **kwargs)
    if not texte:
        raise ErreurOmniRoute(DERNIERE_ERREUR.get(
            "omniroute", "OmniRoute n'a pas fourni de réponse. Vérifiez le fournisseur IA connecté."
        ))
    return texte


def adapter_candidature_omniroots(entreprise_nom, poste_titre, competences="", description=""):
    """Génère le corps du mail via OmniRoute, sans texte de remplacement."""
    messages = [
        {"role": "system", "content": "Tu rédiges des e-mails de candidature de stage en français, "
                                      "professionnels, sincères, 120 à 160 mots, sans inventer d'expérience."},
        {"role": "user", "content": (
            f"Candidate : {PROFIL['nom']}, {PROFIL['titre']}, étudiante ingénieure en Data Science & IA à Marrakech.\n"
            f"Compétences de la candidate : {', '.join(PROFIL['competences'])}.\n"
            f"Entreprise : {entreprise_nom}\nPoste : {poste_titre}\n"
            f"Compétences demandées : {competences}\nDescription : {description}\n\n"
            "Rédige uniquement le corps du mail (de « Madame, Monsieur, » jusqu'à la signature). "
            "Mentionne que le CV et la lettre sont en pièces jointes."
        )},
    ]
    return _exiger_texte_omniroute(messages)


def calculer_match(competences_offre, titre="", description=""):
    """Retourne (score_pct, competences_communes, explication)."""
    demandees = [c.strip().lower() for c in str(competences_offre).split(",") if c.strip()]
    mine = set(PROFIL["competences"])
    communes = [c for c in demandees if any(c in m or m in c for m in mine)]
    score = int(round(100 * len(communes) / len(demandees))) if demandees else 50
    messages = [
        {"role": "system", "content": "Tu es un recruteur technique. Réponds en une phrase française, 25 mots maximum."},
        {"role": "user", "content": (
            f"Profil : {', '.join(PROFIL['competences'])}.\nOffre : {titre}. Compétences : {competences_offre}.\n"
            f"Compétences communes : {', '.join(communes) or 'aucune'}.\n"
            "Donne un conseil concret pour renforcer la candidature."
        )},
    ]
    explication = _exiger_texte_omniroute(messages, max_tokens=120, timeout=20)
    return score, communes, explication


# ------------------------------------------------------------------
# EXTRACTION D'E-MAILS
# ------------------------------------------------------------------
SITES_IGNORES = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "youtube.com", "tiktok.com", "wa.me", "maps.google")


def extraire_emails_du_site(website_url):
    if not website_url or not str(website_url).startswith("http"):
        return None
    if any(d in website_url.lower() for d in SITES_IGNORES):
        return None
    pages = [website_url, urllib.parse.urljoin(website_url, "/contact")]
    headers = {"User-Agent": "Mozilla/5.0"}
    pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    trouves = set()
    for page in pages:
        try:
            req = urllib.request.Request(page, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as r:
                html = r.read().decode("utf-8", errors="ignore")
            for mail in re.findall(pattern, html):
                m = mail.lower().strip().rstrip(".")
                if not any(x in m for x in (".png", ".jpg", ".jpeg", ".svg", ".webp", "w3.org", "example", "sentry")):
                    trouves.add(m)
            rh = [m for m in trouves if any(k in m for k in ("recrutement", "rh", "careers", "job", "contact"))]
            if rh:
                return rh[0]
        except Exception:
            continue
    return next(iter(trouves), None)


def obtenir_email_normalise(nom_entreprise, website_url):
    """Retourne (email, verifie). verifie=False si l'adresse est seulement estimée."""
    reel = extraire_emails_du_site(website_url)
    if reel:
        return reel, True
    domaine = None
    if website_url and str(website_url).startswith("http"):
        try:
            domaine = urllib.parse.urlparse(website_url).netloc.replace("www.", "")
        except Exception:
            pass
    if not domaine or len(domaine) < 3:
        propre = re.sub(r"[^a-z0-9]", "", nom_entreprise.lower())
        domaine = f"{propre}.ma"
    return f"recrutement@{domaine}", False


# ------------------------------------------------------------------
# COLLECTE
# ------------------------------------------------------------------
DERNIERE_ERREUR = {}


def chercher_places_api(query, api_key):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ("places.id,places.displayName,places.formattedAddress,places.location,"
                             "places.rating,places.userRatingCount,places.websiteUri,"
                             "places.nationalPhoneNumber,places.primaryType"),
    }
    payload = {"textQuery": query, "languageCode": "fr", "regionCode": "MA", "pageSize": 20}
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json().get("places", [])
        DERNIERE_ERREUR["google"] = f"Google Places HTTP {res.status_code} : {res.text[:200]}"
        print(DERNIERE_ERREUR["google"])
    except Exception as e:
        DERNIERE_ERREUR["google"] = f"Erreur réseau Google Places : {e}"
        print(DERNIERE_ERREUR["google"])
    return []


def _ligne(place_id, nom, titre, adresse, tel, email, verifie, site, note, avis, lat, lng,
           categorie, source, quartier, modele, date_pub="Récemment"):
    return {
        "place_id": place_id, "nom": nom, "titre_offre": titre, "adresse": adresse,
        "telephone": tel, "email_contact": email, "email_verifie": verifie,
        "site_web": site, "note": note, "nombre_avis": avis, "latitude": lat,
        "longitude": lng, "categorie": categorie, "source": source,
        "domaine": modele["domaine"], "quartier": quartier, "type_stage": "Stage PFE",
        "remuneration": modele["remuneration"], "duree": modele["duree"],
        "description": modele["description"], "competences": modele["competences"],
        "missions": modele["missions"], "profil_requis": modele["profil"],
        "date_publication": date_pub,
    }


def _coord():
    return 31.6295 + (random.random() - 0.5) * 0.02, -7.9811 + (random.random() - 0.5) * 0.02


def collecter_jawb(ville="Marrakech"):
    """Lit le flux RSS public Jawb prévu par le site pour suivre ses annonces."""
    url = "https://jawb.ma/rss.xml"
    try:
        res = requests.get(url, params={"ville": ville},
                           headers={"User-Agent": "MarrakechStage/1.0 (lecteur RSS)"}, timeout=15)
        if res.status_code != 200:
            DERNIERE_ERREUR["jawb"] = f"Flux RSS Jawb HTTP {res.status_code}"
            return pd.DataFrame()
        root = ET.fromstring(res.content)
    except Exception as exc:
        DERNIERE_ERREUR["jawb"] = f"Erreur de lecture du flux RSS Jawb : {exc}"
        return pd.DataFrame()

    offres, vus = [], set()
    modele_vide = {"domaine": "Informatique", "remuneration": "Non précisée", "duree": "Non précisée",
                   "description": "", "competences": "", "missions": "", "profil": ""}
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    for item in root.findall(".//item"):
        def champ(nom):
            el = item.find(nom)
            return "" if el is None or el.text is None else el.text.strip()

        titre, lien = champ("title"), champ("link")
        if not titre or not lien or lien in vus:
            continue
        vus.add(lien)
        description = champ("description")
        contenu = item.find("content:encoded", ns)
        if contenu is not None and contenu.text:
            description = contenu.text.strip()
        description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        texte = f"{titre} {description}".casefold()
        # Le flux peut contenir des emplois classiques : ne conserver que les
        # stages en informatique/data, sujet de cette application.
        mots_stage = ("stage", "stagiaire", "intern", "pfe")
        mots_it = ("informatique", "data", "python", "dévelop", "develop", "logiciel",
                   "digital", "ia", "intelligence artificielle", "sql", "power bi", "tech")
        if not any(m in texte for m in mots_stage) or not any(m in texte for m in mots_it):
            continue
        entreprise = champ("company") or champ("author") or "Entreprise (voir l'annonce)"
        date_pub = champ("pubDate")
        offres.append(_ligne(
            f"jawb_{abs(hash(lien))}", entreprise, titre, ville, "", "", False, lien,
            "", 0, 31.6295, -7.9811, "Offre Jawb", "Jawb", ville, modele_vide,
            date_pub or "Récemment"))
        offres[-1]["description"] = description
        contract = champ("category")
        if contract:
            offres[-1]["type_stage"] = contract
    return pd.DataFrame(offres)


def collecter_linkedin(keywords=("Data", "Informatique", "Développeur", "Stage"), ville="Marrakech"):
    offres, headers = [], {"User-Agent": "Mozilla/5.0"}
    for kw in keywords:
        url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
               f"?keywords={kw}&location={ville}&start=0")
        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")
            for idx, job in enumerate(soup.find_all("li")):
                t = job.find("h3", class_=re.compile("base-search-card__title"))
                c = job.find("h4", class_=re.compile("base-search-card__subtitle"))
                l = job.find("a", class_=re.compile("base-card__full-link"))
                d = job.find("time")
                if not (t and c and l):
                    continue
                titre, entreprise = t.get_text(strip=True), c.get_text(strip=True)
                lien = l["href"].split("?")[0]
                modele = {"domaine": "Informatique", "remuneration": "Non précisée", "duree": "Non précisée",
                          "description": "Consultez l'annonce originale.", "competences": "",
                          "missions": "", "profil": ""}
                lat, lng, q = 31.6295, -7.9811, "Marrakech"
                offres.append(_ligne(
                    f"linkedin_{abs(hash(lien))}", entreprise,
                    titre, "Marrakech",
                    "", "", False, lien, "", 0, lat, lng,
                    "Offre LinkedIn", "LinkedIn", q, modele,
                    d.get_text(strip=True) if d else "Récemment"))
        except Exception as exc:
            DERNIERE_ERREUR["linkedin"] = f"Erreur LinkedIn ({kw}) : {exc}"
    if not offres and "linkedin" not in DERNIERE_ERREUR:
        DERNIERE_ERREUR["linkedin"] = "Aucune offre retournée (résultats vides ou accès refusé)."
    return pd.DataFrame(offres)


def nettoyer_donnees(df_brut):
    if df_brut.empty:
        return df_brut
    df = df_brut.copy()
    df["_n"] = df["nom"].astype(str).str.lower().str.strip()
    df["_t"] = df["titre_offre"].astype(str).str.lower().str.strip()
    df = df.drop_duplicates(subset=["_n", "_t"]).drop(columns=["_n", "_t"])
    df["note"] = pd.to_numeric(df["note"], errors="coerce").fillna(4.5)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce").fillna(31.6295)
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce").fillna(-7.9811)
    for col in COLONNES:
        if col not in df.columns:
            df[col] = ""
    return df[COLONNES]


def _email_estime(nom, site):
    domaine = None
    if site and str(site).startswith("http"):
        try:
            domaine = urllib.parse.urlparse(site).netloc.replace("www.", "")
        except Exception:
            pass
    if not domaine or len(domaine) < 3:
        domaine = re.sub(r"[^a-z0-9]", "", nom.lower()) + ".ma"
    return f"recrutement@{domaine}", False


def executer_collecte_complete(api_key, queries=DEFAULT_QUERIES, progress=None, budget_s=75):
    """Collecte en parallèle (Google Places pour les entreprises, LinkedIn et Jawb pour les annonces).
    budget_s : durée max pour la partie e-mails/web ; au-delà, les e-mails restants sont estimés.
    progress(fraction, texte) : callback facultatif pour afficher l'avancement."""
    maj = progress or (lambda p, t: None)
    DERNIERE_ERREUR.clear()
    maj(0.05, "Recherche des entreprises sur Google Maps...")
    with ThreadPoolExecutor(max_workers=max(1, len(queries))) as ex:
        resultats = list(ex.map(lambda q: chercher_places_api(q, api_key), queries))

    uniques, vus = [], set()
    for i, places in enumerate(resultats):
        for idx, place in enumerate(places):
            pid = place.get("id")
            if pid and pid not in vus:
                vus.add(pid)
                uniques.append((i, idx, place))
    maj(0.2, f"{len(uniques)} entreprises trouvées. Recherche des e-mails RH et des offres...")

    pool = ThreadPoolExecutor(max_workers=16)
    f_emails = {pool.submit(obtenir_email_normalise, p.get("displayName", {}).get("text", ""),
                            p.get("websiteUri", "")): k for k, (_, _, p) in enumerate(uniques)}
    # Collecteurs d'annonces : LinkedIn et flux public Jawb.
    f_web = [pool.submit(collecter_linkedin), pool.submit(collecter_jawb)]
    tous = list(f_emails) + f_web
    fin = time.time() + budget_s
    faits = 0
    try:
        for fut in as_completed(tous, timeout=budget_s):
            faits += 1
            maj(0.2 + 0.7 * faits / len(tous), f"Traitement {faits}/{len(tous)}...")
    except FuturesTimeout:
        maj(0.9, "Délai atteint : les e-mails restants sont estimés.")
    pool.shutdown(wait=False, cancel_futures=True)

    lignes = []
    for fut, k in f_emails.items():
        i, idx, place = uniques[k]
        nom = place.get("displayName", {}).get("text", "")
        site = place.get("websiteUri", "")
        email, verifie = fut.result() if fut.done() and not fut.cancelled() and not fut.exception() else _email_estime(nom, site)
        loc = place.get("location", {})
        modele = POSTES_VARIATION[(i + idx) % len(POSTES_VARIATION)]
        adresse = place.get("formattedAddress", "Marrakech")
        quartier = next((qt for qt in QUARTIERS if qt.lower() in adresse.lower()), "Guéliz")
        lignes.append(_ligne(
            place.get("id"), nom, modele["titre"], adresse, place.get("nationalPhoneNumber", ""), email, verifie, site,
            place.get("rating", 4.5), place.get("userRatingCount", 0), loc.get("latitude", 31.6295),
            loc.get("longitude", -7.9811), place.get("primaryType", "Informatique"), "Google Places", quartier, modele))
    dfs = [pd.DataFrame(lignes)] if lignes else []
    for fut in f_web:
        if fut.done() and not fut.cancelled() and not fut.exception():
            df = fut.result()
            if not df.empty:
                dfs.append(df)
    if not dfs:
        erreurs = [DERNIERE_ERREUR[k] for k in ("linkedin", "jawb") if DERNIERE_ERREUR.get(k)]
        if erreurs:
            DERNIERE_ERREUR["offres"] = " ; ".join(erreurs)
        else:
            DERNIERE_ERREUR["offres"] = "Aucune annonce retournée par LinkedIn ou Jawb."
        return pd.DataFrame()
    maj(0.95, "Enregistrement...")
    df_propre = nettoyer_donnees(pd.concat(dfs, ignore_index=True))
    df_propre.to_csv(CSV_ENTREPRISES, index=False, encoding="utf-8-sig")
    maj(1.0, "Terminé")
    return df_propre


# ------------------------------------------------------------------
# SUIVI
# ------------------------------------------------------------------
def initialiser_fichier_suivi(df_entreprises):
    """Crée le suivi, ou y ajoute les nouvelles offres sans écraser l'existant."""
    if df_entreprises.empty:
        return
    nouveau = pd.DataFrame({
        "place_id": df_entreprises["place_id"].astype(str),
        "nom": df_entreprises["nom"],
        "titre_offre": df_entreprises["titre_offre"],
        "source": df_entreprises["source"] if "source" in df_entreprises.columns else "Inconnue",
        "statut": "À postuler", "canal": "Email", "notes": "",
    })
    if os.path.exists(CSV_SUIVI):
        ancien = pd.read_csv(CSV_SUIVI, dtype={"place_id": str})
        nouveau = nouveau[~nouveau["place_id"].isin(ancien["place_id"])]
        nouveau = pd.concat([ancien, nouveau], ignore_index=True)
    nouveau.to_csv(CSV_SUIVI, index=False, encoding="utf-8-sig")


def mettre_a_jour_statut(place_id, nouveau_statut, canal, notes):
    if not os.path.exists(CSV_SUIVI):
        return False
    df = pd.read_csv(CSV_SUIVI, dtype=str).fillna("")
    mask = df["place_id"] == str(place_id)
    if not mask.any():
        return False
    df.loc[mask, ["statut", "canal", "notes"]] = [str(nouveau_statut), str(canal), str(notes)]
    df.to_csv(CSV_SUIVI, index=False, encoding="utf-8-sig")
    return True


# ------------------------------------------------------------------
# E-MAIL : API Gmail (HTTPS, port 443) au lieu de SMTP
# ------------------------------------------------------------------
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_CREDENTIALS = _cfg("GMAIL_CREDENTIALS_FILE", "credentials.json")  # téléchargé depuis Google Cloud (ID client OAuth « Application de bureau »)
GMAIL_TOKEN = _cfg("GMAIL_TOKEN_FILE", "token.json")                    # créé automatiquement après la première autorisation
MSG_LIBS_GOOGLE = (
    "Bibliothèques Google absentes de l'environnement Python qui exécute l'application. "
    f"Installez-les avec : \"{sys.executable}\" -m pip install "
    "google-api-python-client google-auth-oauthlib"
)
TAILLE_MAX_PJ = 18 * 1024 * 1024  # limite Gmail 25 Mo, base64 compris


def gmail_statut():
    """Retourne (état, message) : 'pret', 'a_autoriser' ou 'credentials_manquant'."""
    if os.path.exists(GMAIL_TOKEN):
        return "pret", "✅ Gmail autorisé : l'envoi se fait par l'API Gmail (HTTPS), depuis votre adresse."
    if os.path.exists(GMAIL_CREDENTIALS):
        return "a_autoriser", ("Gmail pas encore autorisé : au premier envoi, une page Google s'ouvre dans votre navigateur. "
                               "Choisissez votre compte et acceptez, puis revenez ici.")
    return "credentials_manquant", (f"Fichier « {GMAIL_CREDENTIALS} » introuvable à côté d'app.py. Activez Gmail API dans Google Cloud, "
                                    "créez un ID client OAuth « Application de bureau » et téléchargez le JSON sous ce nom.")


def _sauver_token(creds):
    with open(GMAIL_TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def _gmail_creds():
    """Identifiants enregistrés (rafraîchis si besoin) ou None. Un jeton révoqué/expiré est supprimé."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not os.path.exists(GMAIL_TOKEN):
        return None
    try:
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, GMAIL_SCOPES)
    except Exception:
        os.remove(GMAIL_TOKEN)
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # autorisation expirée (mode « Test » : 7 jours) ou révoquée
            os.remove(GMAIL_TOKEN)
            return None
        _sauver_token(creds)  # une panne réseau lève une autre exception : le jeton est conservé
        return creds
    os.remove(GMAIL_TOKEN)
    return None


def autoriser_gmail():
    """Ouvre la page d'autorisation Google dans le navigateur de CE PC, puis enregistre token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS, GMAIL_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", timeout_seconds=240,
                                  success_message="Autorisation réussie. Vous pouvez fermer cet onglet et revenir dans l'application.")
    _sauver_token(creds)
    return creds


def _message_mime(destinataire, sujet, corps, expediteur, fichiers):
    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = expediteur, destinataire, sujet
    msg.attach(MIMEText(corps, "plain", "utf-8"))
    taille = 0
    for chemin in fichiers:
        if chemin and os.path.exists(chemin):
            with open(chemin, "rb") as f:
                data = f.read()
            taille += len(data)
            part = MIMEApplication(data, Name=os.path.basename(chemin))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(chemin)}"'
            msg.attach(part)
    return msg, taille


def _erreur_http_gmail(e):
    statut = getattr(getattr(e, "resp", None), "status", None)
    detail = str(e)
    if statut == 403 and ("accessNotConfigured" in detail or "has not been used" in detail or "disabled" in detail):
        return ("L'API Gmail n'est pas activée sur votre projet Google Cloud : ouvrez « API et services » > « Bibliothèque », "
                "cherchez « Gmail API » et cliquez sur Activer, puis réessayez dans une minute.")
    if statut in (401, 403):
        if os.path.exists(GMAIL_TOKEN):
            os.remove(GMAIL_TOKEN)
        return "Autorisation Gmail refusée ou expirée. Cliquez de nouveau sur Envoyer : la page d'autorisation Google va se rouvrir."
    if statut == 400:
        return f"Gmail refuse le message (adresse du destinataire invalide ?) : {detail[:160]}"
    if statut == 429:
        return "Limite d'envoi Gmail atteinte pour le moment : réessayez plus tard."
    return f"Erreur de l'API Gmail (HTTP {statut}) : {detail[:160]}"


def envoyer_email_candidature(destinataire, sujet, corps, expediteur, fichier_cv=None, fichier_lettre=None):
    """Envoie le message (avec CV et lettre en pièces jointes) via l'API Gmail. Retourne (ok, message)."""
    if not destinataire or "@" not in destinataire:
        return False, "Adresse du recruteur invalide."
    msg, taille = _message_mime(destinataire, sujet, corps, expediteur, (fichier_cv, fichier_lettre))
    if taille > TAILLE_MAX_PJ:
        return False, "Les pièces jointes dépassent 18 Mo : Gmail refusera le message. Réduisez la taille des PDF."
    etat, msg_etat = gmail_statut()
    if etat == "credentials_manquant":
        return False, msg_etat
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as e:
        return False, f"{MSG_LIBS_GOOGLE} (import impossible : {e})"
    try:
        creds = _gmail_creds()
        if creds is None:
            try:
                creds = autoriser_gmail()
            except Exception as e:
                return False, ("Autorisation Google non terminée (" + str(e)[:120] + "). Vérifiez que votre adresse Gmail est ajoutée comme "
                               "« utilisateur de test » dans l'écran de consentement OAuth, puis réessayez.")
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True, "E-mail envoyé avec succès (API Gmail) avec CV et lettre de motivation !"
    except HttpError as e:
        return False, _erreur_http_gmail(e)
    except Exception as e:
        return False, ("Impossible de joindre l'API Gmail (" + str(e)[:140] + "). Vérifiez votre connexion Internet ; "
                       "l'API utilise HTTPS (port 443), comme un site web.")


def construire_eml(destinataire, sujet, corps, expediteur, fichiers=()):
    """Message complet (avec pièces jointes) au format .eml, à ouvrir dans Outlook / Thunderbird."""
    msg, _ = _message_mime(destinataire, sujet, corps, expediteur, fichiers)
    msg["X-Unsent"] = "1"  # Outlook l'ouvre comme brouillon modifiable
    return msg.as_bytes()


# ==================================================================
# V2 : profil, analyse CV, génération d'e-mails, suivi (tableau de bord)
# ==================================================================
import uuid
from datetime import date

FICHIER_PROFIL = "profil.json"
CSV_SUIVI_V2 = "suivi.csv"
STATUTS = ["Envoyé", "Relance à faire", "Entretien", "Offre reçue"]
TONS = ["Professionnel", "Dynamique", "Audacieux"]

COMPETENCES_CONNUES = [
    "Python", "SQL", "Power BI", "Pandas", "Scikit-Learn", "DAX", "FastAPI", "Machine Learning",
    "Gemini API", "Looker Studio", "Talend", "MySQL", "Deep Learning", "Computer Vision", "SVM",
    "Linear Regression", "Gradient Boosting", "Data Warehouse", "Data Visualization", "PyTorch",
    "ETL", "Docker", "NLP", "Tableau", "Spark", "Airflow", "Snowflake", "Git", "Streamlit", "React",
    "Django", "PostgreSQL", "TensorFlow", "Excel", "Kubernetes", "AWS", "Azure",
]

PROFIL_TYPE = {
    "nom": "Lina Zahiri", "titre": "Data Analyst / IA", "email": "linazahiri225@gmail.com",
    "telephone": "", "etudes": "Élève ingénieure, Data Science & Intelligence Artificielle, Marrakech",
    "objectif": "Stage PFE ou pré-embauche à Marrakech en Data Analyst, BI ou ingénierie IA.",
    "cv_text": ("LINA ZAHIRI\nASSISTANTE DATA ANALYST\n\nPROFIL\nÉtudiante en Analyse de Données, motivée et passionnée "
                "par la valorisation des données et l'intelligence artificielle. Connaissances en Python, SQL, Talend, "
                "Machine Learning, Deep Learning et visualisation de données. Je souhaite réaliser un stage PFE "
                "pour mettre mes compétences en pratique."),
    "lettre_text": "",
    "skills": ["Python", "SQL", "Power BI", "Pandas", "Scikit-Learn", "DAX", "FastAPI", "Machine Learning",
               "Gemini API", "Looker Studio", "Talend", "MySQL", "Deep Learning", "Computer Vision", "SVM",
               "Linear Regression", "Gradient Boosting", "Data Warehouse", "Data Visualization",
               "Statistiques", "Analyse de données", "Esprit analytique"],
}


def charger_profil():
    if os.path.exists(FICHIER_PROFIL):
        try:
            with open(FICHIER_PROFIL, encoding="utf-8") as f:
                return {**PROFIL_TYPE, **json.load(f)}
        except Exception:
            pass
    return dict(PROFIL_TYPE)


def sauver_profil(profil):
    with open(FICHIER_PROFIL, "w", encoding="utf-8") as f:
        json.dump(profil, f, ensure_ascii=False, indent=2)


def _correspond(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def extraire_competences(cv_text):
    """Compétences détectées dans le CV (liste connue ; OmniRoute en complément si dispo)."""
    trouvees = [c for c in COMPETENCES_CONNUES if re.search(rf"(?<!\w){re.escape(c)}(?!\w)", cv_text, re.I)]
    rep = appeler_omniroute([
        {"role": "system", "content": "Réponds uniquement par une liste séparée par des virgules."},
        {"role": "user", "content": f"Liste les compétences techniques (outils, langages) de ce CV :\n{cv_text[:4000]}"},
    ], max_tokens=200, timeout=25)
    if rep:
        trouvees += [c.strip() for c in rep.split(",") if 1 < len(c.strip()) < 30]
    vus, out = set(), []
    for c in trouvees:
        if c.lower() not in vus:
            vus.add(c.lower())
            out.append(c)
    return out


def _json_depuis_texte(txt):
    try:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def analyser_cv(cv_text, skills, titre, competences_cible, description=""):
    """Calcule le score de compétences et exige une synthèse IA valide, sans texte de remplacement."""
    demandees = [c.strip() for c in str(competences_cible).split(",") if c.strip()]
    communes, manquantes = [], []
    for c in demandees:
        ok = any(_correspond(c, s) for s in skills) or bool(re.search(rf"(?<!\w){re.escape(c)}(?!\w)", cv_text, re.I))
        (communes if ok else manquantes).append(c)
    score = round(100 * len(communes) / len(demandees)) if demandees else 0
    rep = appeler_omniroute([
        {"role": "system", "content": "Tu es recruteur tech à Marrakech. Réponds en JSON strict : "
                                      '{"resume": "1 phrase", "recommandations": ["3 conseils courts"]}'},
        {"role": "user", "content": f"Poste: {titre}\nDescription: {description}\nCompétences demandées: {competences_cible}\n"
                                    f"Compétences du candidat: {', '.join(skills)}\nCV: {cv_text[:2500]}\n"
                                    f"Communes: {communes}\nManquantes: {manquantes}"},
    ], max_tokens=400, timeout=40)
    data = _json_depuis_texte(rep) if rep else None
    if (not isinstance(data, dict) or not isinstance(data.get("resume"), str)
            or not data["resume"].strip() or not isinstance(data.get("recommandations"), list)
            or not data["recommandations"]):
        DERNIERE_ERREUR["omniroute"] = (
            "OmniRoute n'a pas renvoyé une synthèse et des recommandations valides. "
            "Vérifiez le fournisseur et le modèle connectés, puis réessayez."
        )
        raise ErreurOmniRoute(DERNIERE_ERREUR["omniroute"])
    return {"score": score, "communes": communes, "manquantes": manquantes,
            "resume": data["resume"].strip(),
            "recommandations": [str(r) for r in data["recommandations"][:4]], "ia": True}


def generer_email(profil, entreprise, poste, ton="Professionnel", spontanee=False, competences="", description=""):
    """Retourne (sujet, corps)."""
    cible = "une candidature spontanée pour un stage" if spontanee else f"le poste « {poste} »"
    sujet = (f"Candidature spontanée - Stage Data / IA - {profil['nom']}" if spontanee
             else f"Candidature Stage - {poste} - {profil['nom']}")
    consignes = {"Professionnel": "ton sobre, formel et courtois",
                 "Dynamique": "ton énergique et positif, phrases courtes",
                 "Audacieux": "ton direct et confiant, avec une proposition de valeur claire en première phrase"}[ton]
    corps = _exiger_texte_omniroute([
        {"role": "system", "content": f"Tu rédiges des e-mails de candidature de stage en français, {consignes}, "
                                      "120 à 160 mots, sans inventer d'expérience ni de diplôme."},
        {"role": "user", "content": (
            f"Candidat(e): {profil['nom']}, {profil['titre']}. Études: {profil['etudes']}.\n"
            f"Compétences: {', '.join(profil['skills'])}.\nObjectif: {profil['objectif']}\n"
            f"Entreprise: {entreprise}\nObjet: {cible}\nCompétences demandées: {competences}\nDescription: {description}\n"
            "Écris uniquement le corps du mail (de « Madame, Monsieur, » à la signature), "
            "en mentionnant le CV et la lettre en pièces jointes.")},
    ])
    return sujet, corps


# ---------------- Suivi ----------------
COLS_SUIVI = ["id", "nom", "titre", "type", "email", "date", "statut", "notes"]


def charger_suivi():
    if os.path.exists(CSV_SUIVI_V2):
        return pd.read_csv(CSV_SUIVI_V2, dtype=str).fillna("")
    return pd.DataFrame(columns=COLS_SUIVI)


def ajouter_suivi(nom, titre, type_, email, statut="Envoyé", notes=""):
    df = charger_suivi()
    ligne = {"id": uuid.uuid4().hex[:8], "nom": nom, "titre": titre, "type": type_, "email": email,
             "date": date.today().isoformat(), "statut": statut, "notes": notes}
    pd.concat([df, pd.DataFrame([ligne])], ignore_index=True).to_csv(CSV_SUIVI_V2, index=False, encoding="utf-8-sig")


def changer_statut_suivi(id_, statut):
    df = charger_suivi()
    df.loc[df["id"] == id_, "statut"] = statut
    df.to_csv(CSV_SUIVI_V2, index=False, encoding="utf-8-sig")


def supprimer_suivi(id_):
    df = charger_suivi()
    df[df["id"] != id_].to_csv(CSV_SUIVI_V2, index=False, encoding="utf-8-sig")
