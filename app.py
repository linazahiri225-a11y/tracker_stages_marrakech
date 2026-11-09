"""Interface Streamlit de MarrakechStage.

Ce module construit les écrans et gère les interactions utilisateur.
La logique métier (collecte, IA, Gmail et suivi) est dans backend.py.
Voir README_STRUCTURE.md pour une carte de l'application et du code.
"""
import html
import io
import os
import unicodedata
from datetime import date

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import backend

st.set_page_config(page_title="MarrakechStage - Hub Stages & Entreprises IT", page_icon="🧭", layout="wide", initial_sidebar_state="collapsed")

CV_PATH, LETTRE_PATH = "mon_cv.pdf", "ma_lettre_motivation.pdf"
T_OFFRES, T_CARTE, T_CV, T_ANALYSE, T_EMAIL, T_SUIVI = (
    "Offres de Stage", "Carte & Entreprises IT", "Mon CV & Lettre", "Analyseur IA",
    "Email & Candidature", "Suivi Candidatures")
MOIS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
COULEURS_STATUT = {"Envoyé": "#3b82f6", "Relance à faire": "#f59e0b", "Entretien": "#a855f7", "Offre reçue": "#10b981"}
M_OFFRE, M_ENT = "Cibler une Offre de Stage (LinkedIn / Indeed / Stagiaire.ma)", "Cibler une Entreprise IT (Candidature Spontanée)"
E_OFFRE, E_SPONT = "Postuler à une Offre Spécifique", "Candidature Spontanée (Entreprise IT)"


def e(v):
    return html.escape(str(v))


def norm(texte):
    """minuscules + sans accents, pour une recherche tolérante."""
    return "".join(c for c in unicodedata.normalize("NFD", str(texte).lower()) if unicodedata.category(c) != "Mn")


def recherche(df, texte, colonnes):
    """Garde les lignes où TOUS les mots saisis apparaissent dans au moins une des colonnes."""
    mots = norm(texte).split()
    if not mots or df.empty:
        return df
    cols = [c for c in colonnes if c in df.columns]
    foin = df[cols].astype(str).agg(" ".join, axis=1).map(norm)
    masque = pd.Series(True, index=df.index)
    for m in mots:
        masque &= foin.str.contains(m, regex=False)
    return df[masque]


# ==========================================
# DONNÉES
# ==========================================
COLS_OFFRE = ["place_id", "nom", "titre_offre", "source", "type_stage", "date_publication", "duree", "remuneration",
              "description", "competences", "missions", "profil_requis", "domaine", "adresse", "quartier",
              "email_contact", "site_web", "telephone", "categorie", "latitude", "longitude"]


def charger_offres():
    """Lit le CSV collecté s'il est exploitable (colonnes de base présentes), sinon données de démonstration.
    Les colonnes manquantes sont complétées pour ne jamais planter sur un ancien fichier."""
    chemins = [backend.CSV_ENTREPRISES] if os.path.exists(backend.CSV_ENTREPRISES) else []
    # Charge les résultats de collecte persistés; les colonnes manquantes
    # sont ajoutées afin que les anciens fichiers restent lisibles.
    if chemins:
        try:
            df = pd.concat([pd.read_csv(p).fillna("") for p in chemins], ignore_index=True)
        except Exception:
            df = pd.DataFrame()
        if not df.empty and {"nom", "titre_offre"} <= set(df.columns):
            for col in COLS_OFFRE:
                if col not in df.columns:
                    df[col] = ""
            df["place_id"] = df["place_id"].astype(str)
            df.loc[df["place_id"].isin(["", "nan"]), "place_id"] = [f"csv_{i}" for i in df.index[df["place_id"].isin(["", "nan"])]]
            # une même entreprise (même place_id) peut apparaître dans plusieurs requêtes : on rend chaque offre unique
            rang = df.groupby("place_id").cumcount()
            doublon = df["place_id"].duplicated(keep=False)
            df.loc[doublon, "place_id"] = df.loc[doublon, "place_id"] + "_" + rang[doublon].astype(str)
            df = df.reset_index(drop=True)
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce").fillna(31.6295)
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce").fillna(-7.9811)
            return df
    return pd.DataFrame(columns=COLS_OFFRE)  # rien collecté pour l'instant


def charger_entreprises(df_offres):
    """Prépare les entreprises pour l'écran Carte à partir des données chargées."""
    d = df_offres.drop_duplicates("nom").copy()
    d["secteur"] = d["categorie"].replace("", "Informatique")
    d["effectif"] = "N/C"
    est_entreprise = d["source"].astype(str).str.casefold() == "google places"
    d["technologies"] = d["competences"].where(~est_entreprise, "")
    d["opportunite"] = d["titre_offre"].where(~est_entreprise, "Entreprise à contacter")
    return d.reset_index(drop=True)


profil = st.session_state.setdefault("profil", backend.charger_profil())
st.session_state.setdefault("tab", T_OFFRES)
DONNEES = charger_offres()
# Google Places fournit des entreprises, pas des annonces de stage. Ne les compte
# donc pas comme des offres : elles restent disponibles dans l'onglet Carte.
OFFRES = DONNEES[DONNEES["source"].astype(str).str.casefold() != "google places"].copy()
ENTS = charger_entreprises(DONNEES)
OFFRE_PAR_ID = {r["place_id"]: r.to_dict() for _, r in OFFRES.iterrows()}
ENT_PAR_NOM = {r["nom"]: r.to_dict() for _, r in ENTS.iterrows()}


def libelle_offre(pid):
    o = OFFRE_PAR_ID[pid]
    return f"[{o['source']}] {o['titre_offre']} - {o['nom']}"


def goto(tab, **etat):
    st.session_state.update(etat)
    st.session_state.tab = tab


def sauver_profil():
    st.session_state.profil["cv_text"] = st.session_state.get("cv_text", profil["cv_text"])
    st.session_state.profil["lettre_text"] = st.session_state.get("lettre_text", profil["lettre_text"])
    for k in ("nom", "titre", "email", "telephone", "etudes", "objectif"):
        if f"pf_{k}" in st.session_state:
            st.session_state.profil[k] = st.session_state[f"pf_{k}"]
    if "skills_sel" in st.session_state:
        st.session_state.profil["skills"] = list(st.session_state.skills_sel)
    backend.sauver_profil(st.session_state.profil)


def ajouter_skill(nom=None):
    nom = (nom or st.session_state.get("new_skill", "")).strip()
    if nom and nom.lower() not in [s.lower() for s in st.session_state.profil["skills"]]:
        st.session_state.profil["skills"].append(nom)
        st.session_state.skills_sel = list(st.session_state.profil["skills"])
        sauver_profil()
    st.session_state.new_skill = ""


def charger_profil_type():
    st.session_state.profil = dict(backend.PROFIL_TYPE)
    for k in ("cv_text", "lettre_text", "skills_sel", "pf_nom", "pf_titre", "pf_email", "pf_telephone", "pf_etudes", "pf_objectif"):
        st.session_state.pop(k, None)
    backend.sauver_profil(st.session_state.profil)


# ==========================================
# CSS
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { --brand:#a14a07; --brand-d:#7c3a06; --ink:#1c1917; --mut:#78716c; --line:#e7e5e4; }
html, body, [class*="css"], .stApp { font-family:'Inter',sans-serif; }
.stApp { background:#f7f6f4; }
header[data-testid="stHeader"] { display:none; }
.block-container { max-width:1400px; padding:1rem 2.5rem 3rem; }
/* boutons */
button[data-testid="stBaseButton-primary"] { background:var(--brand); border:1px solid var(--brand); color:#fff; border-radius:10px; font-weight:600; }
button[data-testid="stBaseButton-primary"]:hover { background:var(--brand-d); border-color:var(--brand-d); color:#fff; }
button[data-testid="stBaseButton-secondary"] { background:#f5f5f4; border:1px solid var(--line); color:#292524; border-radius:10px; font-weight:600; }
button[data-testid="stBaseButton-secondary"]:hover { border-color:var(--brand); color:var(--brand); }
button[data-testid="stBaseButton-tertiary"] { color:var(--mut); font-weight:500; }
/* cartes */
div[data-testid="stVerticalBlockBorderWrapper"] { background:#fff; border:1px solid var(--line); border-radius:16px; }
/* navigation */
.st-key-nav button { border:none; background:transparent; color:#57534e; font-weight:600; font-size:14px; }
.st-key-nav button[data-testid="stBaseButton-primary"] { background:var(--brand); color:#fff; }
.st-key-nav { border-bottom:2px solid #fde68a; padding-bottom:8px; margin-bottom:18px; }
/* bannières */
[class*="st-key-hero_"] { background:linear-gradient(110deg,#fff7ed 30%,#fed7aa 100%); border:1px solid #fdba74; border-radius:18px; padding:30px 34px; margin-bottom:18px; }
[class*="st-key-hero_"] h1 { color:#431407; font-size:30px; font-weight:800; margin:10px 0 8px; padding:0; letter-spacing:-.5px; line-height:1.15; }
[class*="st-key-hero_"] p.sub { color:#44403c; font-size:15px; line-height:1.55; max-width:760px; margin:0; }
[class*="st-key-hero_"] p.sub b { color:#a14a07; }
[class*="st-key-action_"] { background:transparent; padding:0; }
[class*="st-key-action_"] button { background:#a14a07; border:1px solid #a14a07; }
[class*="st-key-action_"] button p { color:#fff; font-weight:600; }
.pill { display:inline-block; background:#fff; border:1px solid #fdba74; color:#a14a07; padding:5px 13px; border-radius:20px; font-size:12px; font-weight:700; }
/* badges */
.b { color:#fff; padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600; }
.b-linkedin{background:#2563eb}.b-indeed{background:#312e81}.b-stagiaire{background:#047857}.b-google{background:#7c3aed}
.b-type { background:#fef3c7; color:#b45309; padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600; }
.sal { background:#dcfce7; color:#15803d; padding:3px 10px; border-radius:8px; font-size:13px; font-weight:600; }
.tag { font-family:ui-monospace,Menlo,monospace; background:#f5f5f4; color:#44403c; border:1px solid var(--line);
       padding:3px 10px; border-radius:7px; font-size:12px; display:inline-block; margin:0 6px 6px 0; }
.tag.ok { background:#dcfce7; border-color:#86efac; color:#166534; }
.tag.no { background:#ffedd5; border-color:#fdba74; color:#9a3412; }
.tag.me { background:#fff7ed; border-color:#fdba74; color:var(--brand); }
.brand { font-size:22px; font-weight:800; color:var(--ink); letter-spacing:-.4px; }
.brand span { color:var(--brand); }
.logo { width:44px; height:44px; border-radius:12px; background:linear-gradient(135deg,#d97706,#a14a07); color:#fff;
        display:flex; align-items:center; justify-content:center; font-size:22px; }
.chip { border:1px solid var(--line); background:#fff; border-radius:12px; padding:8px 14px; display:flex; gap:10px; align-items:center; }
.avatar { width:34px; height:34px; border-radius:50%; background:#d97706; color:#fff; font-weight:700; display:flex; align-items:center; justify-content:center; }
.lbl { font-size:11px; font-weight:700; color:#a8a29e; text-transform:uppercase; letter-spacing:.4px; }
.mini { background:#fafaf9; border:1px solid var(--line); border-radius:10px; padding:10px 12px; font-size:13px; }
.mini.hl { background:#fffbeb; border-color:#fde68a; }
.opp { background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:12px 14px; font-size:13px; color:#78350f; }
.empty { text-align:center; padding:34px 10px; color:var(--mut); }
.empty h4 { color:var(--ink); margin:8px 0 4px; }
.kpi { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px 18px; }
.kpi .v { font-size:30px; font-weight:800; line-height:1.1; }
.ring { width:150px; height:150px; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:auto; }
.ring div { width:112px; height:112px; border-radius:50%; background:#fff; display:flex; flex-direction:column; align-items:center; justify-content:center; }
.bar { height:22px; background:#f1f1ef; border-radius:12px; overflow:hidden; }
.bar > div { height:100%; border-radius:12px; color:#fff; font-size:12px; font-weight:700; text-align:right; padding-right:8px; line-height:22px; }
/* thème clair forcé (même si Streamlit / le navigateur est en mode sombre) */
.stApp { color:#1c1917; color-scheme:light; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"], label, .stRadio label p, .stCheckbox label p { color:#1c1917; }
[data-testid="stCaptionContainer"] { color:#78716c; }
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"], textarea, input {
  background:#fff !important; color:#1c1917 !important; -webkit-text-fill-color:#1c1917 !important; }
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { border:1px solid #e7e5e4 !important; border-radius:10px !important; }
input::placeholder, textarea::placeholder { color:#a8a29e !important; -webkit-text-fill-color:#a8a29e !important; }
[data-baseweb="select"] svg { fill:#57534e; }
[data-baseweb="popover"] li, [data-baseweb="popover"] div[role="option"] { color:#1c1917; background:#fff; }
div[role="radiogroup"] label { background:#f5f5f4; border-radius:20px; padding:4px 14px; margin-right:6px; }
div[role="radiogroup"] label:has(input:checked) { background:var(--brand); }
div[role="radiogroup"] label:has(input:checked) p { color:#fff; }
div[role="radiogroup"] label > div:first-child { display:none; }
[data-baseweb="tab"] p { color:#44403c; }
[data-testid="stSidebar"] { background:#fff; }
[data-testid="stSidebar"] * { color:#1c1917; }
/* fenêtres modales (st.dialog) : fond blanc, texte foncé */
[data-testid="stDialog"] div[role="dialog"] { background:#fff !important; color:#1c1917 !important; color-scheme:light; border-radius:16px; }
[data-testid="stDialog"] div[role="dialog"] :is(h1,h2,h3,h4,p,li,label,summary) { color:#1c1917 !important; }
[data-testid="stDialog"] div[role="dialog"] .lbl { color:#a8a29e !important; }
[data-testid="stDialog"] div[role="dialog"] .b { color:#fff !important; }
[data-testid="stDialog"] div[role="dialog"] .b-type { color:#b45309 !important; }
[data-testid="stDialog"] button[aria-label="Close"], [data-testid="stDialog"] button[aria-label="Close"] svg { color:#1c1917 !important; fill:#1c1917 !important; }
[data-testid="stDialog"] a[data-testid^="stBaseLinkButton"] { background:#f5f5f4 !important; border:1px solid #e7e5e4 !important; color:#1c1917 !important; border-radius:10px; }
[data-testid="stDialog"] a[data-testid^="stBaseLinkButton"] p { color:#1c1917 !important; }
[data-testid="stDialog"] button[data-testid="stBaseButton-primary"] p { color:#fff !important; }
.stMultiSelect [data-baseweb="tag"] { background:#fff7ed; border:1px solid #fdba74; color:var(--brand); font-family:ui-monospace,monospace; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# COMPOSANTS
# ==========================================
def hero(cle, pill, titre, texte, action=None):
    """Bannière sombre ; action = (libellé, callback, args)."""
    with st.container(key=f"hero_{cle}"):
        c1, c2 = st.columns([4, 1.2]) if action else (st.container(), None)
        with c1:
            st.markdown(f'<span class="pill">{pill}</span><h1>{titre}</h1><p class="sub">{texte}</p>', unsafe_allow_html=True)
        if action and c2:
            with c2:
                st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
                st.button(action[0], on_click=action[1], args=action[2], key=f"action_{cle}", use_container_width=True)


def badge_source(s):
    cls = {"LinkedIn": "b-linkedin", "Indeed": "b-indeed", "Stagiaire.ma": "b-stagiaire"}.get(s, "b-google")
    return f'<span class="b {cls}">{e(s or "Offre")}</span>'


def tags(csv, classe=""):
    return "".join(f'<span class="tag {classe}">{e(c.strip())}</span>' for c in str(csv).split(",") if c.strip())


def fr_date(iso):
    try:
        d = date.fromisoformat(iso)
        return f"{d.day} {MOIS[d.month - 1]} {d.year}"
    except Exception:
        return iso


def pieces_jointes():
    return [p for p in (CV_PATH, LETTRE_PATH) if os.path.exists(p)]


def lire_pdf(fichier):
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(fichier).pages).strip()
    except Exception:
        return ""


# ==========================================
# MODALES
# ==========================================
@st.dialog("Détails de l'offre de stage", width="large")
def dialogue_offre(o):
    st.markdown(f'{badge_source(o.get("source"))} <span class="b-type" style="margin-left:6px">{e(o.get("quartier", ""))}</span>',
                unsafe_allow_html=True)
    st.markdown(f"## {o['titre_offre']}")
    st.markdown(f"**{o['nom']}** · 📍 {o.get('adresse', '')}")
    st.markdown(f"""<div class="mini hl" style="display:flex;gap:30px;flex-wrap:wrap">
      <div><span class="lbl">Rémunération</span><br><b style="color:#15803d">{e(o.get('remuneration', ''))}</b></div>
      <div><span class="lbl">Durée</span><br><b>{e(o.get('duree', ''))}</b></div>
      <div><span class="lbl">Contact</span><br><b style="color:#2563eb">{e(o.get('email_contact', ''))}</b></div></div>""",
                unsafe_allow_html=True)
    st.markdown("**Description**")
    st.write(o.get("description", ""))
    for titre, cle in (("Missions", "missions"), ("Profil requis", "profil_requis")):
        st.markdown(f"**{titre}**")
        for ligne in str(o.get(cle, "")).split("\n"):
            if ligne.strip():
                st.markdown(f"• {ligne.strip()}")
    st.markdown(tags(o.get("competences", "")), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.button("✈️ Préparer l'email IA", type="primary", use_container_width=True, key=f"dlg_em_{o['place_id']}",
              on_click=goto, args=(T_EMAIL,), kwargs={"em_mode": E_OFFRE, "em_offre": o["place_id"]})
    if str(o.get("site_web", "")).startswith("http"):
        c2.link_button("🌐 Voir l'annonce originale", o["site_web"], use_container_width=True)


@st.dialog("Détail de la candidature")
def dialogue_suivi(r):
    st.markdown(f"### {r['titre']}\n**{r['nom']}** · {r['type']} · {fr_date(r['date'])}")
    st.write(f"✉️ {r['email']}")
    st.write(f"Statut : **{r['statut']}**")
    if r["notes"]:
        st.write(r["notes"])


# ==========================================
# COLLECTE & CONFIGURATION IA (visible dans l'onglet Offres)
# ==========================================
def panneau_collecte():
    """Lance le backend, puis conserve son bilan afin de l'afficher après le rerun Streamlit."""
    ancien_bilan = st.session_state.pop("bilan_collecte", None)
    if ancien_bilan:
        st.warning(ancien_bilan)
    if st.button("🔄 Lancer la collecte", type="primary", key="btn_collecte"):
        if not backend.GOOGLE_MAPS_API_KEY:
            st.error("Aucune clé Google Maps : renseignez GOOGLE_MAPS_API_KEY dans config.py.")
            return
        barre = st.progress(0.0, text="Démarrage de la collecte...")
        res = backend.executer_collecte_complete(backend.GOOGLE_MAPS_API_KEY, progress=lambda p, t: barre.progress(p, text=t))
        barre.empty()
        if res.empty:
            details = backend.DERNIERE_ERREUR.get("offres") or backend.DERNIERE_ERREUR.get("google") or "Aucune annonce réelle trouvée."
            st.session_state.bilan_collecte = "Aucun résultat. " + details
            st.rerun()
        else:
            comptes = res["source"].value_counts().to_dict()
            bilan = "Collecte terminée. Résultats par source : " + " · ".join(f"{s}: {n}" for s, n in comptes.items())
            for src in ("LinkedIn", "Jawb"):
                if src not in comptes:
                    msg = backend.DERNIERE_ERREUR.get(src.casefold().replace("stagiaires.ma", "stagiaires"), "Aucun résultat retourné.")
                    bilan += f"\n{src} : 0 — {msg}"
            st.session_state.bilan_collecte = bilan
            st.rerun()


# ==========================================
# EN-TÊTE + NAVIGATION
# ==========================================
st.markdown('<div style="display:flex;gap:12px;align-items:center;margin-bottom:14px"><div class="logo">🧭</div><div>'
            '<div class="brand">Marrakech<span>Stage</span> <span class="b-type" style="font-size:10px;padding:2px 8px">IT & IA</span></div>'
            '<div style="font-size:13px;color:#78736d">Hub Stages & Entreprises IT à Marrakech</div></div></div>', unsafe_allow_html=True)

NAV = [(T_OFFRES, f"💼 Offres de Stage · {len(OFFRES)}"), (T_CARTE, f"📍 Carte & Entreprises IT · {len(ENTS)}"),
       (T_CV, "👤 Mon CV & Lettre"), (T_ANALYSE, "✨ Analyseur IA"), (T_EMAIL, "✈️ Email & Candidature"),
       (T_SUIVI, "✅ Suivi Candidatures")]
with st.container(key="nav"):
    for col, (nom, label) in zip(st.columns(len(NAV)), NAV):
        col.button(label, key=f"nav_{nom}", use_container_width=True, on_click=goto, args=(nom,),
                   type="primary" if st.session_state.tab == nom else "secondary")
tab = st.session_state.tab

# Aucune donnée collectée : on propose uniquement la collecte (les onglets CV et Suivi restent utilisables)
if DONNEES.empty and tab in (T_OFFRES, T_CARTE, T_ANALYSE, T_EMAIL):
    hero("vide", "🔄 Première utilisation", "Aucune offre pour le moment",
         "Cliquez sur « Lancer la collecte » pour récupérer les entreprises IT de Marrakech (Google Maps), "
         "les e-mails RH et les offres de stage. La collecte prend environ une à deux minutes.")
    panneau_collecte()
    st.stop()

# ==========================================
# 1. OFFRES
# ==========================================
if tab == T_OFFRES:
    # Écran 1 : recherche, filtres par source et affichage des annonces.
    hero("offres", "✨ Agrégateur Exclusif Marrakech • Data & IA", "Trouvez votre Stage IT & IA / Data Analyst à Marrakech",
         "Les annonces réelles collectées depuis les sources configurées. Les entreprises trouvées sur Google Maps "
         "sont affichées dans l'onglet Carte, séparément des offres. Générez vos candidatures avec l'IA.")
    panneau_collecte()
    with st.container(border=True):
        s1, s2 = st.columns([4, 2.2])
        mot = s1.text_input("Recherche", placeholder="🔍  Rechercher par titre, compétence (Python, SQL, Power BI, DAX...), entreprise...  puis appuyez sur Entrée",
                            label_visibility="collapsed")
        sources_disponibles = sorted(OFFRES["source"].dropna().astype(str).unique().tolist())
        sources_filtre = ["LinkedIn", "Jawb"]
        choix_sources = ["Toutes"] + list(dict.fromkeys(sources_filtre + sources_disponibles))
        source = s2.radio("Source", choix_sources, horizontal=True, label_visibility="collapsed")
        f1, f2, f3 = st.columns(3)
        domaine = f1.selectbox("Domaine d'expertise", ["Tous les domaines"] + sorted(d for d in OFFRES["domaine"].unique() if d))
        quartier = f2.selectbox("Quartier à Marrakech", ["Tous les quartiers"] + backend.QUARTIERS)
        type_stage = f3.selectbox("Type de stage", ["Tous les types"] + sorted(t for t in OFFRES["type_stage"].unique() if t))

    st.caption("Google Maps fournit les entreprises. Les annonces sont recherchées automatiquement sur LinkedIn et via le flux RSS public Jawb.")

    df = OFFRES.copy()
    if source != "Toutes":
        df = df[df["source"] == source]
    if domaine != "Tous les domaines":
        df = df[df["domaine"] == domaine]
    if quartier != "Tous les quartiers":
        df = df[df["quartier"].astype(str).str.contains(quartier, case=False)]
    if type_stage != "Tous les types":
        df = df[df["type_stage"] == type_stage]
    df = recherche(df, mot, ("titre_offre", "nom", "competences", "domaine", "quartier", "adresse", "description", "type_stage"))

    st.markdown(f"<p style='color:#78716c;margin:14px 4px'>Affichage de <b style='color:#1c1917'>{len(df)}</b> offre(s) à Marrakech</p>",
                unsafe_allow_html=True)
    if df.empty:
        if source != "Toutes" and source not in set(OFFRES["source"].astype(str)):
            st.info(f"Aucune offre collectée depuis {source} pour le moment. Les entreprises Google Maps sont consultables dans l'onglet Carte.")
        else:
            st.info("Aucune offre ne correspond à ces filtres.")
    for _, r in df.iterrows():
        o = r.to_dict()
        with st.container(border=True):
            g, d = st.columns([3.6, 1])
            g.markdown(f"""
            <div>{badge_source(o['source'])} <span class="b-type" style="margin-left:4px">{e(o['type_stage'])}</span>
              <span style="color:#a8a29e;font-size:13px;margin-left:6px">• {e(o.get('date_publication', ''))}</span></div>
            <h3 style="margin:10px 0 6px;font-size:20px;font-weight:700;color:#1c1917">{e(o['titre_offre'])}</h3>
            <div style="font-size:14px;color:#57534e;margin-bottom:10px"><b>{e(o['nom'])}</b> &nbsp; 📍 {e(o.get('quartier', ''))}, Marrakech
              &nbsp; 📅 {e(o.get('duree', ''))} &nbsp; <span class="sal">$ {e(o.get('remuneration', ''))}</span></div>
            <p style="color:#57534e;font-size:14px;line-height:1.55;margin-bottom:12px">{e(o.get('description', ''))}</p>
            <div>{tags(o.get('competences', ''))}</div>""", unsafe_allow_html=True)
            pid = o["place_id"]
            d.button("✈️ Préparer l'Email IA", key=f"em_{pid}", type="primary", use_container_width=True,
                     on_click=goto, args=(T_EMAIL,), kwargs={"em_mode": E_OFFRE, "em_offre": pid})
            d.button("✨ Tester le Match IA", key=f"mt_{pid}", use_container_width=True,
                     on_click=goto, args=(T_ANALYSE,), kwargs={"an_mode": M_OFFRE, "an_offre": pid, "an_run": True})
            if d.button("ⓘ Voir détails complets", key=f"dt_{pid}", type="tertiary", use_container_width=True):
                dialogue_offre(o)

# ==========================================
# 2. CARTE & ENTREPRISES
# ==========================================
elif tab == T_CARTE:
    # Écran 2 : entreprises de Google Maps représentées sur une carte Folium.
    hero("carte", "📍 Collecteur & Cartographie Google Maps • Marrakech", "Entreprises IT & Laboratoires IA à Marrakech",
         "Localisez toutes les structures tech basées à Marrakech (Guéliz, Hivernage, Sidi Ghanem). Obtenez l'email direct "
         "du recruteur et postulez instantanément en candidature spontanée avec l'IA.")
    with st.container(border=True):
        a, b, c = st.columns([3, 1, 1])
        q = a.text_input("Recherche", placeholder="🔍  Rechercher par nom, tech (Python, Power BI...), quartier...  puis appuyez sur Entrée", label_visibility="collapsed", key="ent_q")
        qt = b.selectbox("Quartier", ["Tous les quartiers"] + backend.QUARTIERS, label_visibility="collapsed")
        sect = c.selectbox("Secteur", ["Toutes"] + sorted(ENTS["secteur"].astype(str).unique()), label_visibility="collapsed")
    E = ENTS.copy()
    E = recherche(E, q, ("nom", "technologies", "quartier", "adresse", "secteur", "description"))
    if qt != "Tous les quartiers":
        E = E[E["quartier"] == qt]
    if sect != "Toutes":
        E = E[E["secteur"] == sect]

    noms = list(E["nom"])
    if st.session_state.get("ent_sel") not in noms:
        st.session_state.ent_sel = noms[0] if noms else None

    gauche, droite = st.columns([1.15, 1])
    with gauche:
        with st.container(border=True):
            st.markdown(f"**🗺️ Carte interactive de Marrakech** ({len(E)} répertoriées) — _cliquez sur un marqueur_")
            fm = folium.Map(location=[31.6420, -8.0050], zoom_start=12, tiles="OpenStreetMap")
            for _, r in E.iterrows():
                try:
                    folium.Marker([float(r["latitude"]), float(r["longitude"])], tooltip=r["nom"],
                                  icon=folium.Icon(color="orange" if r["nom"] != st.session_state.ent_sel else "red",
                                                   icon="briefcase", prefix="fa")).add_to(fm)
                except (TypeError, ValueError):
                    continue
            res = st_folium(fm, height=420, use_container_width=True, returned_objects=["last_object_clicked_tooltip"])
            clic = (res or {}).get("last_object_clicked_tooltip")
            if clic and clic != st.session_state.get("dernier_clic") and clic in noms:
                st.session_state.dernier_clic = clic
                st.session_state.ent_sel = clic
                st.rerun()
            st.markdown("Quartiers clés : " + "".join(f'<span class="tag">{q_}</span>' for q_ in backend.QUARTIERS), unsafe_allow_html=True)
    with droite:
        sel = ENT_PAR_NOM.get(st.session_state.ent_sel)
        if sel:
            with st.container(border=True):
                st.markdown(f"""
                <span class="b-type">{e(sel['secteur'])}</span>
                <h3 style="margin:8px 0 2px;font-weight:800">{e(sel['nom'])}</h3>
                <div style="color:#78716c;font-size:13px;margin-bottom:10px">📍 {e(sel['adresse'])}</div>
                <div class="mini" style="margin-bottom:10px;color:#57534e">{e(sel['description'])}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
                  <div class="mini hl"><span class="lbl">Email RH</span><br><b style="color:var(--brand)">{e(sel['email_contact'])}</b></div>
                  <div class="mini"><span class="lbl">Téléphone</span><br><b>{e(sel.get('telephone', ''))}</b></div>
                  <div class="mini"><span class="lbl">Site web</span><br><b style="color:var(--brand)">{e(str(sel.get('site_web', '')).replace('https://', ''))}</b></div>
                  <div class="mini"><span class="lbl">Effectif</span><br><b>{e(sel.get('effectif', 'N/C'))}</b></div></div>
                <div style="font-size:13px;font-weight:600;margin-bottom:6px">Technologies & Outils Data / IA :</div>
                <div>{tags(sel.get('technologies', ''))}</div>
                <div class="opp" style="margin-top:6px"><b>💡 Opportunité IA / Data Analyst :</b><br>{e(sel.get('opportunite', ''))}</div>""",
                            unsafe_allow_html=True)
                x, y = st.columns([2, 1])
                x.button("✈️ Postuler avec Email Personnalisé IA", type="primary", use_container_width=True, key="ent_post",
                         on_click=goto, args=(T_EMAIL,), kwargs={"em_mode": E_SPONT, "em_ent": sel["nom"]})
                y.button("✨ Matcher mon CV", use_container_width=True, key="ent_match",
                         on_click=goto, args=(T_ANALYSE,), kwargs={"an_mode": M_ENT, "an_ent": sel["nom"], "an_run": True})
        with st.container(border=True):
            st.markdown(f"**ANNUAIRE RAPIDE MARRAKECH ({len(E)})**")
            with st.container(height=300, border=False):
                for n in noms:
                    r = ENT_PAR_NOM[n]
                    st.button(f"{n}  ·  {r['quartier']}  —  {str(r['technologies']).split(',')[0]}", key=f"dir_{n}",
                              use_container_width=True, type="primary" if n == st.session_state.ent_sel else "secondary",
                              on_click=lambda n=n: st.session_state.update(ent_sel=n, dernier_clic=n))

# ==========================================
# 3. CV & LETTRE
# ==========================================
elif tab == T_CV:
    # Écran 3 : profil candidat et documents CV/lettre de motivation.
    hero("cv", "👤 Candidat Data & IA • Marrakech", "Mon Profil, CV & Lettre de Motivation",
         "Personnalisez vos compétences en IA et Data Analytics. L'IA adaptera automatiquement votre CV et lettre pour "
         "chaque entreprise ou offre à Marrakech.", action=("🔄 Charger profil type Marrakech", charger_profil_type, ()))
    t1, t2, t3 = st.tabs(["📄 Mon CV & Résumé Technique", "🏅 Lettre de Motivation", "🎓 Coordonnées & Études"])
    with t1:
        cg, cd = st.columns([2.1, 1])
        with cg, st.container(border=True):
            st.markdown("**Contenu de mon CV**")
            st.caption("Collez ou chargez votre CV. L'IA s'en servira pour analyser les correspondances avec les stages à Marrakech.")
            up = st.file_uploader("Importer mon CV (PDF seulement)", type=["pdf"], key="up_cv")
            if up and st.session_state.get("cv_vu") != up.file_id:
                st.session_state.cv_vu = up.file_id
                with open(CV_PATH, "wb") as f:
                    f.write(up.getbuffer())
                texte = lire_pdf(CV_PATH)
                if texte:
                    st.session_state.cv_text = texte
                sauver_profil()
                st.success("CV enregistré (il sera joint à vos e-mails).")
            st.text_area("CV", value=profil["cv_text"], height=330, key="cv_text", label_visibility="collapsed", on_change=sauver_profil)
            b1, b2, b3 = st.columns([1.2, 1, 1.5])
            b1.download_button("⬇️ Télécharger mon CV (.txt)", st.session_state.get("cv_text", profil["cv_text"]), "mon_cv.txt", use_container_width=True)
            if b3.button("✨ Analyser mon CV avec l'IA", type="primary", use_container_width=True):
                trouvees = backend.extraire_competences(st.session_state.cv_text)
                nouvelles = [c for c in trouvees if c.lower() not in [s.lower() for s in profil["skills"]]]
                for c in nouvelles:
                    profil["skills"].append(c)
                st.session_state.skills_sel = list(profil["skills"])
                sauver_profil()
                st.success(f"{len(nouvelles)} compétence(s) ajoutée(s) : {', '.join(nouvelles) or 'aucune nouvelle'}")
        with cd:
            with st.container(border=True):
                st.markdown("**Compétences Techniques & Outils**")
                st.caption("Ces mots-clés sont comparés aux exigences des offres de stage à Marrakech. Cliquez sur × pour retirer.")
                n1, n2 = st.columns([4, 1])
                n1.text_input("Ajouter", placeholder="ex: Scikit-learn, Tableau...", key="new_skill", label_visibility="collapsed",
                              on_change=ajouter_skill)
                n2.button("＋", on_click=ajouter_skill, key="add_skill", type="primary")
                st.multiselect("Compétences", options=profil["skills"], default=profil["skills"], key="skills_sel",
                               label_visibility="collapsed", on_change=sauver_profil)
                sugg = [s for s in ("PyTorch", "ETL", "Docker", "NLP") if s.lower() not in [x.lower() for x in profil["skills"]]]
                if sugg:
                    st.caption("Suggestions pour Data Analyst / IA à Marrakech :")
                    for col, s in zip(st.columns(len(sugg)), sugg):
                        col.button(f"+ {s}", key=f"sg_{s}", on_click=ajouter_skill, args=(s,), use_container_width=True)
            with st.container(border=True):
                st.markdown(f"**🎯 Objectif de Stage :**\n\n{profil['objectif']}")
                st.button("✈️ Passer à l'envoi d'emails", type="primary", use_container_width=True, on_click=goto, args=(T_EMAIL,), key="cv_to_mail")
    with t2:
        with st.container(border=True):
            up = st.file_uploader("Importer ma lettre de motivation (PDF)", type=["pdf"], key="up_lm")
            if up and st.session_state.get("lm_vu") != up.file_id:
                st.session_state.lm_vu = up.file_id
                with open(LETTRE_PATH, "wb") as f:
                    f.write(up.getbuffer())
                texte = lire_pdf(LETTRE_PATH)
                if texte:
                    st.session_state.lettre_text = texte
                sauver_profil()
                st.success("Lettre enregistrée (elle sera jointe à vos e-mails).")
            st.text_area("Texte de la lettre (optionnel, pour référence)", value=profil["lettre_text"], height=300,
                         key="lettre_text", on_change=sauver_profil)
    with t3:
        with st.container(border=True):
            a, b = st.columns(2)
            a.text_input("Nom complet", value=profil["nom"], key="pf_nom", on_change=sauver_profil)
            b.text_input("Titre / spécialité", value=profil["titre"], key="pf_titre", on_change=sauver_profil)
            a.text_input("E-mail", value=profil["email"], key="pf_email", on_change=sauver_profil)
            b.text_input("Téléphone", value=profil["telephone"], key="pf_telephone", on_change=sauver_profil)
            st.text_input("Études", value=profil["etudes"], key="pf_etudes", on_change=sauver_profil)
            st.text_area("Objectif de stage", value=profil["objectif"], key="pf_objectif", on_change=sauver_profil)

# ==========================================
# 4. ANALYSEUR IA
# ==========================================
elif tab == T_ANALYSE:
    # Écran 4 : analyse du CV et adéquation avec une offre via OmniRoute.
    hero("analyse", "✨ Analyseur Prédictif IA • OmniRoute", "Matching IA : CV vs Offre & Entreprise à Marrakech",
         "L'intelligence artificielle analyse votre CV et vos compétences au regard des exigences du recruteur, détecte les "
         "compétences clés manquantes et formule des recommandations adaptées au marché tech de Marrakech.")
    st.session_state.setdefault("an_mode", M_OFFRE)
    with st.container(border=True):
        a, b = st.columns([3, 1])
        mode = a.radio("Mode", [M_OFFRE, M_ENT], horizontal=True, label_visibility="collapsed", key="an_mode")
        lancer = b.button("✨ Lancer l'Analyse du CV", type="primary", use_container_width=True, key="an_go")
        x, y = st.columns([2, 1])
        if mode == M_OFFRE:
            pid = x.selectbox("Sélectionnez l'offre de stage à Marrakech :", list(OFFRE_PAR_ID), format_func=libelle_offre, key="an_offre")
            o = OFFRE_PAR_ID[pid]
            cible = {"titre": o["titre_offre"], "nom": o["nom"], "competences": o["competences"], "description": o.get("description", ""),
                     "info": f"Entreprise: {o['nom']} • Quartier: {o.get('quartier', '')}"}
        else:
            nom = x.selectbox("Sélectionnez l'entreprise IT :", list(ENT_PAR_NOM), key="an_ent")
            en = ENT_PAR_NOM[nom]
            cible = {"titre": f"Candidature spontanée - {nom}", "nom": nom, "competences": en["technologies"],
                     "description": en["description"], "info": f"Secteur: {en['secteur']} • Quartier: {en['quartier']}"}
        y.markdown(f'<div class="mini"><span class="lbl">Cible active</span><br><b>{e(cible["titre"])}</b><br>'
                   f'<span style="color:#78716c;font-size:12px">{e(cible["info"])}</span></div>', unsafe_allow_html=True)
    if lancer or st.session_state.pop("an_run", False):
        st.session_state.an_res = None
        with st.spinner("Analyse en cours..."):
            try:
                st.session_state.an_res = (cible["titre"], backend.analyser_cv(
                    st.session_state.get("cv_text", profil["cv_text"]), profil["skills"], cible["titre"],
                    cible["competences"], cible["description"]))
                st.session_state.pop("an_err", None)
            except backend.ErreurOmniRoute as exc:
                st.session_state.an_err = str(exc)
    if st.session_state.get("an_err"):
        st.error("Analyse IA non effectuée : " + st.session_state.an_err)
    res = st.session_state.get("an_res")
    if not res or res[0] != cible["titre"]:
        st.markdown('<div class="kpi empty"><div style="font-size:34px">🗂️</div><h4>Prêt pour l\'analyse</h4>'
                    'Cliquez sur « Lancer l\'Analyse du CV » pour comparer vos compétences avec l\'offre ou l\'entreprise sélectionnée.</div>',
                    unsafe_allow_html=True)
    else:
        r = res[1]
        couleur = "#10b981" if r["score"] >= 70 else "#f59e0b" if r["score"] >= 40 else "#ef4444"
        c1, c2 = st.columns([1, 2.4])
        with c1, st.container(border=True):
            st.markdown(f'<div class="ring" style="background:conic-gradient({couleur} {r["score"]}%,#eee 0)"><div>'
                        f'<span style="font-size:32px;font-weight:800">{r["score"]}%</span><span class="lbl">compatibilité</span></div></div>',
                        unsafe_allow_html=True)
        with c2, st.container(border=True):
            st.markdown(f"**Synthèse** {'(rédigée par OmniRoute)' if r['ia'] else ''}\n\n{r['resume']}")
            st.markdown("**✅ Compétences en commun**")
            st.markdown(tags(", ".join(r["communes"]), "ok") or "_Aucune_", unsafe_allow_html=True)
            st.markdown("**📚 Compétences à acquérir**")
            st.markdown(tags(", ".join(r["manquantes"]), "no") or "_Aucune_", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**💡 Recommandations**")
            for rec in r["recommandations"]:
                st.markdown(f"• {rec}")
            st.button("✈️ Rédiger l'email de candidature", type="primary", on_click=goto, args=(T_EMAIL,),
                      kwargs=({"em_mode": E_OFFRE, "em_offre": st.session_state.get("an_offre")} if mode == M_OFFRE
                              else {"em_mode": E_SPONT, "em_ent": st.session_state.get("an_ent")}), key="an_to_mail")

# ==========================================
# 5. EMAIL & CANDIDATURE
# ==========================================
elif tab == T_EMAIL:
    # Écran 5 : génération du message, pièces jointes et envoi Gmail.
    hero("email", "✉️ Générateur d'Emails de Candidature • Marrakech IT", "Email de Candidature Personnalisé par l'IA",
         "Générez un email ultra-ciblé mentionnant la référence de l'offre (LinkedIn, Indeed, Stagiaire.ma) ou une candidature "
         "spontanée mettant en valeur vos compétences (Python, SQL, Power BI) pour les entreprises de Marrakech.")
    st.session_state.setdefault("em_mode", E_OFFRE)
    with st.container(border=True):
        a, b = st.columns([2.2, 1.4])
        mode = a.radio("Mode", [E_OFFRE, E_SPONT], horizontal=True, label_visibility="collapsed", key="em_mode")
        ton = b.radio("Tonalité", backend.TONS, index=1, horizontal=True, key="em_ton")
        x, y = st.columns([3, 1])
        if mode == E_OFFRE:
            pid = x.selectbox("Sélectionnez l'offre de stage visée :", list(OFFRE_PAR_ID), format_func=libelle_offre, key="em_offre")
            o = OFFRE_PAR_ID[pid]
            cib = dict(nom=o["nom"], poste=o["titre_offre"], dest=o.get("email_contact", ""), comp=o["competences"],
                       desc=o.get("description", ""), spont=False, type="Offre de stage", ok=bool(o.get("email_verifie", False)))
        else:
            nom = x.selectbox("Sélectionnez l'entreprise IT :", list(ENT_PAR_NOM), key="em_ent")
            en = ENT_PAR_NOM[nom]
            cib = dict(nom=nom, poste="Stage Data / IA (spontanée)", dest=en["email_contact"], comp=en["technologies"],
                       desc=en["description"], spont=True, type="Candidature spontanée", ok=bool(en.get("email_verifie", False)))
        y.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if y.button("✨ Générer mon Email Personnalisé", type="primary", use_container_width=True):
            for k in ("em_suj", "em_corps", "em_dest", "em_cible"):
                st.session_state.pop(k, None)
            st.session_state.pop("em_ia_err", None)
            with st.spinner("Rédaction en cours..."):
                try:
                    suj, corps = backend.generer_email(profil, cib["nom"], cib["poste"], ton, cib["spont"],
                                                       cib["comp"], cib["desc"])
                    st.session_state.update(em_suj=suj, em_corps=corps, em_dest=cib["dest"], em_cible=cib)
                    st.session_state.pop("em_generation_error", None)
                except backend.ErreurOmniRoute as exc:
                    st.session_state.em_generation_error = str(exc)
    if st.session_state.get("em_generation_error"):
        st.error("E-mail non généré : " + st.session_state.em_generation_error)
    if "em_corps" not in st.session_state:
        st.markdown('<div class="kpi empty"><div style="font-size:34px">✉️</div><h4>Prêt à rédiger votre email de candidature</h4>'
                    'Cliquez sur « Générer mon Email Personnalisé » pour concevoir un email sur-mesure adapté aux besoins de l\'entreprise.</div>',
                    unsafe_allow_html=True)
    else:
        c = st.session_state.em_cible
        with st.container(border=True):
            st.markdown(f"**Brouillon pour {e(c['nom'])}** · {e(c['type'])}")
            if not c["ok"]:
                st.warning("Cette adresse e-mail n'a pas été vérifiée (donnée de démonstration ou estimée). Contrôlez-la avant d'envoyer.")
            st.text_input("Destinataire", key="em_dest")
            st.text_input("Sujet", key="em_suj")
            st.text_area("Message (modifiable)", key="em_corps", height=280)
            pj = pieces_jointes()
            st.caption("📎 Pièces jointes : " + (", ".join(pj) if pj else "aucune (importez votre CV et votre lettre dans « Mon CV & Lettre »)"))
            etat_gm, msg_gm = backend.gmail_statut()
            (st.success if etat_gm == "pret" else st.warning if etat_gm == "credentials_manquant" else st.info)(msg_gm)
            s1, s2 = st.columns(2)
            if s1.button("📨 Envoyer l'e-mail (API Gmail)", type="primary", use_container_width=True):
                with st.spinner("Envoi par l'API Gmail… (la première fois, une page Google s'ouvre pour l'autorisation)"):
                    ok, msg = backend.envoyer_email_candidature(st.session_state.em_dest, st.session_state.em_suj,
                                                                st.session_state.em_corps, profil["email"], CV_PATH, LETTRE_PATH)
                if ok:
                    backend.ajouter_suivi(c["nom"], c["poste"], c["type"], st.session_state.em_dest, "Envoyé")
                    st.success(msg + " Ajouté au suivi.")
                else:
                    st.error(msg)
            if s2.button("💾 Enregistrer sans envoyer (relance à faire)", use_container_width=True):
                backend.ajouter_suivi(c["nom"], c["poste"], c["type"], st.session_state.em_dest, "Relance à faire", "Brouillon")
                st.success("Ajouté au suivi.")
            st.download_button("⬇️ Télécharger le mail avec pièces jointes (.eml)",
                               backend.construire_eml(st.session_state.em_dest, st.session_state.em_suj, st.session_state.em_corps,
                                                      profil["email"], pieces_jointes()),
                               file_name="candidature.eml", mime="message/rfc822")

# ==========================================
# 6. SUIVI
# ==========================================
elif tab == T_SUIVI:
    # Écran 6 : liste des candidatures et mise à jour de leur statut.
    hero("suivi", "📊 Analytics & Suivi des Démarches • Stages Marrakech", "Tableau de Bord & Métriques des Candidatures",
         "Visualisez les statistiques en temps réel de votre campagne de recherche de stage à Marrakech : taux de réponse, "
         "entonnoir de conversion et répartition par type de candidature.",
         action=("✈️ Nouvelle Candidature", goto, (T_EMAIL,)))
    S = backend.charger_suivi()
    n = len(S)
    cnt = {s: int((S["statut"] == s).sum()) for s in backend.STATUTS}
    pos = cnt["Entretien"] + cnt["Offre reçue"]
    pct = lambda v: round(100 * v / n) if n else 0
    k1, k2, k3, k4 = st.columns(4)
    for col, titre, val, sous, coul in (
            (k1, "Candidatures Totales", n, "À Marrakech", "#1c1917"),
            (k2, "Taux d'Entretien", f"{pct(pos)}%", f"{pos} / {n} retours positifs", "#9333ea"),
            (k3, "Offres Obtenues", cnt["Offre reçue"], f"{pct(cnt['Offre reçue'])}% de conversion", "#059669"),
            (k4, "Relances à prévoir", cnt["Relance à faire"], "À relancer sous 5j", "#ea580c")):
        col.markdown(f'<div class="kpi"><span style="color:#78716c;font-size:13px">{titre}</span><div class="v" style="color:{coul}">{val}</div>'
                     f'<span style="color:#a8a29e;font-size:12px">{sous}</span></div>', unsafe_allow_html=True)
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    gl, gr = st.columns([1, 1.25])
    with gl, st.container(border=True):
        st.markdown(f"**Répartition par Statut** <span style='float:right;color:#a8a29e;font-size:12px'>{n} total</span>", unsafe_allow_html=True)
        if n:
            cur, parts = 0, []
            for s in backend.STATUTS:
                p = 100 * cnt[s] / n
                parts.append(f"{COULEURS_STATUT[s]} {cur}% {cur + p}%")
                cur += p
            fond = f"conic-gradient({', '.join(parts)})"
        else:
            fond = "conic-gradient(#e7e5e4 0 100%)"
        d1, d2 = st.columns([1, 1.2])
        d1.markdown(f'<div class="ring" style="background:{fond}"><div><b style="font-size:28px">{n}</b><span class="lbl">dossiers</span></div></div>',
                    unsafe_allow_html=True)
        d2.markdown("".join(f'<div style="display:flex;justify-content:space-between;font-size:13px;margin:7px 0">'
                            f'<span><span style="color:{COULEURS_STATUT[s]}">●</span> {s}</span><b>{cnt[s]} <span style="color:#a8a29e;font-weight:400">{pct(cnt[s])}%</span></b></div>'
                            for s in backend.STATUTS), unsafe_allow_html=True)
    with gr, st.container(border=True):
        st.markdown("**Entonnoir de Conversion Recrutement**")
        etapes = [("1. Candidatures Transmises", n, "#3b82f6"), ("2. En cours de Traitement / Relances", n - cnt["Envoyé"] if n else 0, "#f59e0b"),
                  ("3. Entretiens RH & Techniques", pos, "#a855f7"), ("4. Offres Finales Obtenues", cnt["Offre reçue"], "#10b981")]
        for nom_e, v, coul in etapes:
            st.markdown(f'<div style="display:flex;justify-content:space-between;font-size:12px;font-weight:600;margin-top:8px"><span>{nom_e}</span>'
                        f'<span>{v} ({pct(v)}%)</span></div><div class="bar"><div style="width:{max(pct(v), 3 if v else 0)}%;background:{coul}">{v if v else ""}</div></div>',
                        unsafe_allow_html=True)
        sp = int((S["type"] == "Candidature spontanée").sum())
        st.caption(f"Canaux : Offres d'emploi : {n - sp} · Spontanées : {sp}")

    with st.container(border=True):
        f1, f2 = st.columns([3, 1])
        choix = f1.radio("Filtre", [f"Tous ({n})"] + [f"{s} ({cnt[s]})" for s in backend.STATUTS], horizontal=True, label_visibility="collapsed")
        rech = f2.text_input("Rechercher", placeholder="🔍 Rechercher une entreprise...", label_visibility="collapsed")
    V = S.copy()
    if not choix.startswith("Tous"):
        V = V[V["statut"] == choix.rsplit(" (", 1)[0]]
    if rech:
        V = recherche(V, rech, ("nom", "titre", "email", "type"))
    if V.empty:
        st.info("Aucune candidature pour le moment. Envoyez un e-mail depuis l'onglet « Email & Candidature » : elle apparaîtra ici.")
    for _, r in V.sort_values("date", ascending=False).iterrows():
        with st.container(border=True):
            a, b, c1, c2 = st.columns([5, 1.6, 0.4, 0.4])
            coul = COULEURS_STATUT.get(r["statut"], "#78716c")
            a.markdown(f'<span class="b" style="background:{coul}">{e(r["statut"])}</span> <span class="tag">{e(r["type"])}</span> '
                       f'<span style="color:#78716c;font-size:13px">📅 {fr_date(r["date"])}</span>'
                       f'<div style="font-weight:700;font-size:16px;margin:6px 0 2px">{e(r["titre"])}</div>'
                       f'<div style="font-size:13px;color:#57534e"><b>{e(r["nom"])}</b> &nbsp; <span class="tag">{e(r["email"])}</span></div>',
                       unsafe_allow_html=True)
            nouveau = b.selectbox("Statut", backend.STATUTS, index=backend.STATUTS.index(r["statut"]) if r["statut"] in backend.STATUTS else 0,
                                  key=f"st_{r['id']}", label_visibility="collapsed")
            if nouveau != r["statut"]:
                backend.changer_statut_suivi(r["id"], nouveau)
                st.rerun()
            if c1.button("👁", key=f"v_{r['id']}", help="Voir"):
                dialogue_suivi(r.to_dict())
            if c2.button("🗑", key=f"x_{r['id']}", help="Supprimer"):
                backend.supprimer_suivi(r["id"])
                st.rerun()
