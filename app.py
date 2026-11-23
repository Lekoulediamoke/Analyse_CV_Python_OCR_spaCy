# ==============================================================
# Application web pour les recruteurs : présélection de CV
# Projet : Analyse de CV en apprentissage automatique avec Python, OCR et spaCy
#
# Le recruteur dépose des CV (PDF, scans, photos, Word), règle ses critères,
# et obtient un classement expliqué, des fiches candidats, une comparaison,
# un suivi des candidatures et un export Excel.
#
# En local :   streamlit run app.py
# En ligne :   Streamlit Community Cloud (voir le README)
# ==============================================================

import html
import io
import os
import tempfile
from collections import Counter

import altair as alt
import pandas as pd
import streamlit as st

import pipeline_cv as pc

st.set_page_config(page_title="Présélection de CV", page_icon="🧭", layout="wide")

# La page est en français : on l'indique au navigateur et on bloque sa traduction
# automatique, qui fait planter Streamlit (erreur « insertBefore »)
import streamlit.components.v1 as components
components.html("""<script>
const d = window.parent.document;
d.documentElement.lang = "fr";
d.documentElement.setAttribute("translate", "no");
d.body.classList.add("notranslate");
</script>""", height=0)

COMPETENCES_PROPOSEES = ["Relation client", "Écoute active", "Gestion des réclamations",
                         "Vente additionnelle", "Fidélisation", "Négociation", "Recouvrement",
                         "Appels entrants", "Appels sortants", "Assistance technique",
                         "CRM", "Salesforce", "Zendesk", "Excel", "Pack Office"]
SUIVIS = ["Nouveau", "À contacter", "Entretien prévu", "En attente", "Écarté"]
CRITERES = ["Expérience", "Relation client", "Compétences demandées", "Anglais", "Niveau d'études"]

# Palettes au choix : fond, couleur principale (foncée et moyenne), accent,
# texte sur l'accent, et 5 teintes pour les graphiques
PALETTES = {
    "Émeraude": {"fond": "#F3F6F4", "fonce": "#0E3B3C", "moyen": "#1D6B68", "accent": "#E0A93B",
                 "sur_accent": "#2A1E05", "doux": "#E3EFEC",
                 "graphe": ["#0E3B3C", "#1D6B68", "#4E9C8F", "#E0A93B", "#B9D7CE"]},
    "Prune": {"fond": "#F7F4F7", "fonce": "#35193F", "moyen": "#5E2D6B", "accent": "#E8735F",
              "sur_accent": "#2B0D07", "doux": "#EFE6F1",
              "graphe": ["#35193F", "#5E2D6B", "#9C6AA8", "#E8735F", "#D9C4DE"]},
    "Ardoise": {"fond": "#F2F4F7", "fonce": "#1B2534", "moyen": "#3A4A60", "accent": "#2BB3A3",
                "sur_accent": "#062622", "doux": "#E4E9F0",
                "graphe": ["#1B2534", "#3A4A60", "#7B8BA1", "#2BB3A3", "#BFC9D6"]},
}


def style(p):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
:root {{ --fond:{p['fond']}; --fonce:{p['fonce']}; --moyen:{p['moyen']}; --accent:{p['accent']};
        --sur-accent:{p['sur_accent']}; --doux:{p['doux']}; --encre:#1C2430; --gris:#5B6474;
        --ligne:#E2E5E9; --vert:#1F7A4D; --vert-bg:#E2F3EA; --rouge:#B23A2E; --rouge-bg:#F9E4E1;
        --ambre:#8A5300; --ambre-bg:#FCEFD8; }}
html, body, [class*="css"], .stMarkdown, .stTabs, button, input {{ font-family:'Plus Jakarta Sans', sans-serif; }}
.stApp {{ background: var(--fond); }}
.block-container {{ padding-top: 1.4rem; max-width: 1320px; }}
.banniere {{ background: linear-gradient(125deg, var(--fonce) 0%, var(--moyen) 100%); border-radius: 22px;
            padding: 32px 38px; color: #F4F6F5; margin-bottom: 20px; position: relative; overflow: hidden; }}
.banniere:after {{ content:""; position:absolute; right:-60px; top:-60px; width:260px; height:260px;
                  border-radius:50%; background: var(--accent); opacity:.18; }}
.banniere .sur {{ color: var(--accent); font-weight: 800; letter-spacing: .14em; text-transform: uppercase; font-size: .78rem; }}
.banniere h1 {{ color: #FFFFFF; font-size: 2.2rem; font-weight: 800; margin: 6px 0 8px 0; padding: 0; }}
.banniere p {{ color: #DDE6E3; font-size: 1.02rem; margin: 0; max-width: 820px; }}
.etapes {{ display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; position: relative; z-index: 1; }}
.etape {{ background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); border-radius: 999px;
         padding: 8px 16px; font-size: .9rem; color: #F4F6F5; }}
.etape b {{ background: var(--accent); color: var(--sur-accent); border-radius: 50%; display: inline-block;
           width: 22px; height: 22px; text-align: center; line-height: 22px; margin-right: 8px; font-size: .8rem; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 6px 0 18px 0; }}
.kpi {{ background: #FFFFFF; border-radius: 16px; padding: 16px 20px; border: 1px solid var(--ligne);
       display: flex; gap: 14px; align-items: center; }}
.kpi .icone {{ width: 46px; height: 46px; min-width: 46px; border-radius: 12px; background: var(--doux);
              display: flex; align-items: center; justify-content: center; font-size: 1.3rem; }}
.kpi .val {{ font-size: 1.9rem; font-weight: 800; color: var(--fonce); line-height: 1.05; }}
.kpi .lib {{ color: var(--gris); font-size: .85rem; }}
.carte {{ background: #FFFFFF; border-radius: 18px; padding: 18px 22px; margin-bottom: 12px;
         border: 1px solid var(--ligne); display: flex; gap: 18px; align-items: center; }}
.carte.retenu {{ box-shadow: inset 6px 0 0 var(--vert); }}
.carte.ecarte {{ box-shadow: inset 6px 0 0 var(--rouge); }}
.rang {{ background: var(--fonce); color: #FFFFFF; font-weight: 800; border-radius: 14px; width: 48px; height: 48px;
        min-width: 48px; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; }}
.rang.premier {{ background: var(--accent); color: var(--sur-accent); }}
.corps {{ flex: 1; min-width: 0; }}
.nom {{ font-size: 1.18rem; font-weight: 800; color: var(--encre); }}
.poste {{ color: var(--gris); font-size: .9rem; margin-bottom: 6px; }}
.badge {{ display: inline-block; border-radius: 999px; padding: 3px 11px; font-size: .78rem; font-weight: 700; margin: 2px 6px 2px 0; }}
.badge.ok {{ background: var(--vert-bg); color: var(--vert); }}
.badge.non {{ background: var(--rouge-bg); color: var(--rouge); }}
.badge.alerte {{ background: var(--ambre-bg); color: var(--ambre); }}
.badge.suivi {{ background: var(--doux); color: var(--fonce); }}
.puce {{ display: inline-block; background: var(--fond); color: var(--moyen); border: 1px solid var(--ligne);
        border-radius: 8px; padding: 2px 9px; font-size: .78rem; margin: 4px 4px 0 0; }}
.infos {{ display: flex; gap: 18px; flex-wrap: wrap; color: var(--encre); font-size: .88rem; margin-top: 4px; }}
.infos span b {{ color: var(--gris); font-weight: 600; }}
.score {{ text-align: center; min-width: 120px; }}
.anneau {{ width: 92px; height: 92px; border-radius: 50%; margin: 0 auto; display: flex; align-items: center;
          justify-content: center; }}
.anneau div {{ width: 72px; height: 72px; border-radius: 50%; background: #FFFFFF; display: flex; flex-direction: column;
              align-items: center; justify-content: center; font-weight: 800; font-size: 1.45rem; color: var(--fonce); }}
.anneau small {{ font-size: .68rem; color: var(--gris); font-weight: 600; }}
.titre-section {{ font-size: 1.08rem; font-weight: 800; color: var(--fonce); margin: 16px 0 8px 0;
                 display: flex; align-items: center; gap: 8px; }}
.titre-section:before {{ content:""; width: 8px; height: 22px; border-radius: 4px; background: var(--accent); }}
.ligne-score {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--ligne); font-size: .9rem; }}
.ligne-score b {{ color: var(--fonce); }}
.barre {{ height: 8px; border-radius: 99px; background: var(--doux); margin-top: 4px; }}
.barre div {{ height: 8px; border-radius: 99px; background: var(--moyen); }}
.frise {{ border-left: 3px solid var(--doux); margin-left: 8px; padding-left: 18px; }}
.jalon {{ position: relative; margin-bottom: 14px; }}
.jalon:before {{ content:""; position: absolute; left: -26px; top: 4px; width: 13px; height: 13px; border-radius: 50%;
                background: var(--accent); border: 3px solid #FFFFFF; box-shadow: 0 0 0 2px var(--accent); }}
.jalon .quand {{ color: var(--gris); font-size: .8rem; font-weight: 700; }}
.jalon .quoi {{ font-weight: 700; color: var(--encre); }}
.jalon .ou {{ color: var(--moyen); font-size: .88rem; }}
.colonne-comp {{ background: #FFFFFF; border: 1px solid var(--ligne); border-radius: 18px; padding: 18px 20px; }}
.colonne-comp h4 {{ margin: 0 0 4px 0; color: var(--fonce); font-weight: 800; }}
.colonne-comp .ligne {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--ligne); font-size: .88rem; }}
.colonne-comp .ligne span:first-child {{ color: var(--gris); }}
.avertissement {{ background: var(--ambre-bg); border-radius: 12px; padding: 12px 16px; color: var(--ambre); font-size: .9rem; margin: 6px 0 12px 0; }}
.vide {{ background:#FFFFFF; border:2px dashed var(--ligne); border-radius:18px; padding:34px; text-align:center; color:var(--gris); }}
.vide b {{ color: var(--fonce); font-size: 1.1rem; }}
.pied {{ text-align:center; color: var(--gris); font-size: .8rem; margin-top: 34px; }}
section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid var(--ligne); }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 700; background: #FFFFFF; border-radius: 10px 10px 0 0; padding: 8px 16px; }}
.stTabs [aria-selected="true"] {{ color: var(--fonce) !important; box-shadow: inset 0 -3px 0 var(--accent); }}
</style>"""


e = html.escape            # tout texte venu d'un CV est échappé avant d'être affiché


def bloc(code_html):
    """Affiche du HTML. Les lignes sont collées à gauche : sinon le Markdown
    de Streamlit prendrait les lignes indentées pour du code."""
    st.markdown("\n".join(l.strip() for l in code_html.splitlines() if l.strip()),
                unsafe_allow_html=True)


@st.cache_resource(show_spinner="Préparation de l'outil (la première ouverture peut prendre quelques minutes)…")
def outils():
    return pc.langue_ocr(), pc.preparer_modele_ner()


def analyser(fichiers):
    """fichiers : liste de (nom, contenu en octets)."""
    langue, nlp_ner = outils()
    with tempfile.TemporaryDirectory() as dossier:
        chemins = []
        for nom, contenu in fichiers:
            chemin = os.path.join(dossier, os.path.basename(nom))
            with open(chemin, "wb") as f:
                f.write(contenu)
            chemins.append(chemin)
        return pc.analyser_fichiers(chemins, langue, nlp_ner)


# Suivi et notes gardés à part : Streamlit efface l'état d'un champ qui n'est
# plus affiché (quand on passe d'un candidat à l'autre)
SUIVI = st.session_state.setdefault("suivis", {})
NOTES = st.session_state.setdefault("notes", {})


def suivi(cv):
    return SUIVI.get(cv["fichier"], SUIVIS[0])


def note(cv):
    return NOTES.get(cv["fichier"], "")


def enregistrer(fichier):
    SUIVI[fichier] = st.session_state[f"champ_suivi_{fichier}"]
    NOTES[fichier] = st.session_state[f"champ_note_{fichier}"]


def experience_txt(cv):
    a = cv["annees_experience"]
    return f"{a:.1f} ans".replace(".", ",") if a is not None else "?"


def anneau(score, couleur):
    return (f'<div class="anneau" style="background:conic-gradient({couleur} {score * 3.6}deg, var(--doux) 0)">'
            f'<div>{score}<small>/ 100</small></div></div>')


def carte_candidat(rang, cv, p):
    ev = cv["evaluation"]
    retenu = ev["statut"].startswith("Remplit")
    badges = ('<span class="badge ok">✓ Remplit les critères</span>' if retenu
              else f'<span class="badge non">✗ {e(ev["statut"].replace("Ne remplit pas : ", ""))}</span>')
    if cv["a_verifier"] != "non":
        badges += '<span class="badge alerte">⚠ À vérifier</span>'
    if suivi(cv) != SUIVIS[0]:
        badges += f'<span class="badge suivi">📌 {e(suivi(cv))}</span>'
    puces = "".join(f'<span class="puce">{e(c)}</span>' for c in (cv["competences"] or [])[:6])
    puces += "".join(f'<span class="puce">🌐 {e(l)}</span>' for l in cv["langues"] or [])
    return f"""
<div class="carte {'retenu' if retenu else 'ecarte'}">
<div class="rang {'premier' if rang == 1 else ''}">{rang}</div>
<div class="corps">
<div class="nom">{e(cv['nom'] or cv['fichier'])}</div>
<div class="poste">{e(cv['poste_vise'] or 'Poste visé non indiqué')}</div>
<div>{badges}</div>
<div class="infos"><span><b>Expérience</b> {experience_txt(cv)}</span>
<span><b>Diplôme</b> {e(cv['diplome'] or '?')}</span>
<span><b>Tél.</b> {e(cv['telephone'] or '?')}</span>
<span><b>E-mail</b> {e(cv['email'] or '?')}</span></div>
<div>{puces}</div>
</div>
<div class="score">{anneau(ev['score'], p['moyen'] if retenu else p['accent'])}</div>
</div>"""


# ---------------- Barre latérale : apparence et critères ----------------
with st.sidebar:
    palette = st.radio("🎨 Couleurs", list(PALETTES), horizontal=True)
    p = PALETTES[palette]
    st.markdown(style(p), unsafe_allow_html=True)
    st.divider()
    st.header("🎯 Vos critères")
    st.markdown("**Obligatoires**")
    experience_min = st.slider("Expérience minimum (années)", 0, 10, 1)
    anglais_obligatoire = st.toggle("Anglais obligatoire")
    niveau_min = st.selectbox("Niveau d'études minimum", list(pc.NIVEAUX))
    st.divider()
    st.markdown("**Pour le score**")
    experience_ideale = st.slider("Expérience idéale (années)", 1, 10, 5,
                                  help="À partir de cette durée, le candidat a tous les points d'expérience.")
    competences = st.multiselect("Compétences recherchées", COMPETENCES_PROPOSEES,
                                 default=["Relation client", "CRM"])
    autres = st.text_input("Autres compétences (séparées par des virgules)")
    competences += [c.strip() for c in autres.split(",") if c.strip()]
    st.divider()
    st.caption("🔒 Les CV ne sont pas conservés : ils sont analysés puis supprimés.")

# ---------------- Bannière ----------------
bloc("""
<div class="banniere">
<div class="sur">Recrutement · Conseillers clientèle</div>
<h1>Présélection de CV</h1>
<p>Déposez des CV, réglez vos critères à gauche, puis lisez les candidatures dans l'ordre proposé.
L'outil aide à la lecture : <b>la décision reste au recruteur</b>.</p>
<div class="etapes">
<div class="etape"><b>1</b>Déposer les CV</div>
<div class="etape"><b>2</b>Régler les critères</div>
<div class="etape"><b>3</b>Comparer et suivre</div>
<div class="etape"><b>4</b>Exporter en Excel</div>
</div>
</div>""")

# ---------------- Dépôt des CV ----------------
bloc('<div class="titre-section">Déposer les CV</div>')
fichiers = st.file_uploader("PDF (même scanné), photo (PNG, JPG) ou Word (.docx)",
                            type=[f.strip(".") for f in pc.FORMATS], accept_multiple_files=True)
col1, col2, _ = st.columns([1.2, 1.8, 3])
if col1.button("🔍 Analyser les CV", type="primary", disabled=not fichiers, width="stretch"):
    with st.spinner(f"Analyse de {len(fichiers)} CV…"):
        st.session_state.resultats = analyser([(f.name, f.getvalue()) for f in fichiers])
if col2.button("✨ Essayer avec 4 CV d'exemple (fictifs)", width="stretch"):
    dossier = "cv_exemples"
    exemples = [(n, open(os.path.join(dossier, n), "rb").read()) for n in sorted(os.listdir(dossier))
                if not n.startswith(("~$", "."))]
    with st.spinner("Analyse des CV d'exemple…"):
        st.session_state.resultats = analyser(exemples)

if "resultats" not in st.session_state:
    bloc("""<div class="vide"><b>Aucun CV analysé pour l'instant</b><br>
Déposez vos CV ci-dessus, ou cliquez sur « Essayer avec 4 CV d'exemple » pour découvrir l'outil.</div>""")
    st.stop()

cvs, erreurs, doublons = st.session_state.resultats
for nom, raison in erreurs:
    st.warning(f"{nom} : {raison}")
if doublons:
    st.info(f"{doublons} CV en double (même e-mail ou téléphone) retiré(s).")
if not cvs:
    st.stop()

# ---------------- Évaluation et indicateurs ----------------
for cv in cvs:
    cv["evaluation"] = pc.evaluer(cv, experience_min, experience_ideale, anglais_obligatoire,
                                  niveau_min, competences)
cvs.sort(key=lambda c: (not c["evaluation"]["statut"].startswith("Remplit"),
                        -c["evaluation"]["score"]))
rangs = {cv["fichier"]: i for i, cv in enumerate(cvs, 1)}
noms = [f"{i}. {cv['nom'] or cv['fichier']}" for i, cv in enumerate(cvs, 1)]
retenus = sum(cv["evaluation"]["statut"].startswith("Remplit") for cv in cvs)
a_relire = sum(cv["a_verifier"] != "non" for cv in cvs)
moyenne = round(sum(cv["evaluation"]["score"] for cv in cvs) / len(cvs))

bloc(f"""
<div class="kpis">
<div class="kpi"><div class="icone">📄</div><div><div class="val">{len(cvs)}</div><div class="lib">CV analysés</div></div></div>
<div class="kpi"><div class="icone">✅</div><div><div class="val">{retenus}</div><div class="lib">remplissent les critères</div></div></div>
<div class="kpi"><div class="icone">⚠️</div><div><div class="val">{a_relire}</div><div class="lib">à relire (lecture incertaine)</div></div></div>
<div class="kpi"><div class="icone">📈</div><div><div class="val">{moyenne}</div><div class="lib">score moyen sur 100</div></div></div>
</div>""")

o_classement, o_ensemble, o_fiche, o_comparer, o_export, o_methode = st.tabs(
    ["🏆 Classement", "📊 Vue d'ensemble", "👤 Fiche candidat", "⚖️ Comparer",
     "⬇️ Export", "ℹ️ Méthode"])

# ---------------- Classement, avec filtres ----------------
with o_classement:
    f1, f2, f3 = st.columns([2, 1.3, 1.3])
    recherche = f1.text_input("Rechercher", placeholder="Nom, compétence, poste…")
    seulement = f2.toggle("Seulement ceux qui remplissent les critères")
    filtre_suivi = f3.selectbox("Suivi", ["Tous"] + SUIVIS)
    visibles = []
    for cv in cvs:
        texte = " ".join([cv["nom"] or "", cv["poste_vise"] or ""] + (cv["competences"] or [])).lower()
        if recherche and recherche.lower() not in texte:
            continue
        if seulement and not cv["evaluation"]["statut"].startswith("Remplit"):
            continue
        if filtre_suivi != "Tous" and suivi(cv) != filtre_suivi:
            continue
        visibles.append(cv)
    if visibles:
        bloc("".join(carte_candidat(rangs[cv["fichier"]], cv, p) for cv in visibles))
    else:
        bloc('<div class="vide"><b>Aucun candidat ne correspond à ces filtres</b></div>')

# ---------------- Vue d'ensemble : graphiques ----------------
with o_ensemble:
    g, d = st.columns([1.5, 1])
    with g:
        bloc('<div class="titre-section">D\'où vient le score de chaque candidat</div>')
        lignes = [{"Candidat": cv["nom"] or cv["fichier"], "Critère": critere, "Points": pts,
                   "Rang": rangs[cv["fichier"]]}
                  for cv in cvs for critere, pts in cv["evaluation"]["points"].items()]
        graphe = alt.Chart(pd.DataFrame(lignes)).mark_bar(cornerRadius=3).encode(
            x=alt.X("sum(Points):Q", title="Points (sur 100)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Candidat:N", sort=alt.EncodingSortField(field="Rang", op="min"), title=None),
            color=alt.Color("Critère:N", sort=CRITERES, title=None,
                            scale=alt.Scale(domain=CRITERES, range=p["graphe"]),
                            legend=alt.Legend(orient="bottom", columns=3)),
            order=alt.Order("Critère:N"),
            tooltip=["Candidat", "Critère", "Points"],
        ).properties(height=max(160, 46 * len(cvs)))
        st.altair_chart(graphe, width="stretch")
    with d:
        bloc('<div class="titre-section">Compétences les plus présentes</div>')
        compte = Counter(c for cv in cvs for c in (cv["competences"] or []))
        if compte:
            top = pd.DataFrame(compte.most_common(8), columns=["Compétence", "Candidats"])
            barres = alt.Chart(top).mark_bar(cornerRadius=3, color=p["accent"]).encode(
                x=alt.X("Candidats:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("Compétence:N", sort="-x", title=None),
                tooltip=["Compétence", "Candidats"]).properties(height=280)
            st.altair_chart(barres, width="stretch")
        bloc('<div class="titre-section">Langues</div>')
        langues = Counter(l for cv in cvs for l in (cv["langues"] or []))
        bloc("".join(f'<span class="puce">🌐 {e(l)} · {n}</span>' for l, n in langues.most_common()))

# ---------------- Fiche candidat : détail, frise, suivi ----------------
with o_fiche:
    choix = st.selectbox("Candidat", noms, key="fiche_choix")
    cv = cvs[noms.index(choix)]
    ev = cv["evaluation"]
    bloc(carte_candidat(noms.index(choix) + 1, cv, p))
    if cv["a_verifier"] != "non":
        bloc(f'<div class="avertissement">⚠ À vérifier dans le CV d\'origine : {e(cv["a_verifier"])}</div>')
    gauche, droite = st.columns([1.35, 1])
    with gauche:
        bloc('<div class="titre-section">Parcours professionnel</div>')
        if cv["experiences"]:
            bloc('<div class="frise">' + "".join(
                f'<div class="jalon"><div class="quand">{e(x["Période"] or "Dates non trouvées")}</div>'
                f'<div class="quoi">{e(x["Poste"])}</div>'
                f'<div class="ou">{e(x["Entreprise"] or "Entreprise non trouvée")}</div></div>'
                for x in cv["experiences"]) + "</div>")
        else:
            st.text("\n".join(cv["experience"]) or "Aucune expérience trouvée")
        bloc('<div class="titre-section">Formation</div>')
        if cv["formations"]:
            bloc('<div class="frise">' + "".join(
                f'<div class="jalon"><div class="quand">{e(x["Année"] or "")}</div>'
                f'<div class="quoi">{e(x["Diplôme"])}</div>'
                f'<div class="ou">{e(x["Établissement"] or "")}</div></div>'
                for x in cv["formations"]) + "</div>")
        else:
            st.text("\n".join(cv["formation"]) or "Aucune formation trouvée")
    with droite:
        bloc('<div class="titre-section">Détail du score</div>')
        maximum = dict(zip(CRITERES, [35, 20, 25, 10, 10]))
        lignes = ""
        for (critere, pts), ligne in zip(ev["points"].items(), ev["detail"]):
            libelle = ligne.rpartition("→")[0].strip()
            lignes += (f'<div class="ligne-score"><span>{e(libelle)}</span><b>{pts}/{maximum[critere]}</b></div>'
                       f'<div class="barre"><div style="width:{100 * pts / maximum[critere]:.0f}%"></div></div>')
        lignes += f'<div class="ligne-score"><span><b>Total</b></span><b>{ev["score"]} / 100</b></div>'
        bloc(lignes)
        bloc('<div class="titre-section">Suivi de la candidature</div>')
        f = cv["fichier"]
        st.session_state[f"champ_suivi_{f}"] = suivi(cv)
        st.session_state[f"champ_note_{f}"] = note(cv)
        st.selectbox("Étape", SUIVIS, key=f"champ_suivi_{f}", on_change=enregistrer, args=(f,))
        st.text_area("Note du recruteur", key=f"champ_note_{f}", on_change=enregistrer, args=(f,),
                     placeholder="Ex. : bon contact au téléphone, disponible en janvier…")
        st.caption("Le suivi et les notes apparaissent dans le classement et dans l'export Excel.")

# ---------------- Comparer 2 ou 3 candidats ----------------
with o_comparer:
    choisis = st.multiselect("Candidats à comparer (3 au plus)", noms, default=noms[:min(3, len(noms))],
                             max_selections=3)
    if choisis:
        colonnes = st.columns(len(choisis))
        for colonne, nom in zip(colonnes, choisis):
            cv = cvs[noms.index(nom)]
            ev = cv["evaluation"]
            lignes = "".join(f'<div class="ligne"><span>{e(k)}</span><b>{e(str(v))}</b></div>' for k, v in [
                ("Critères obligatoires", "✓ oui" if ev["statut"].startswith("Remplit") else "✗ non"),
                ("Expérience", experience_txt(cv)),
                ("Diplôme", cv["diplome"] or "?"),
                ("Langues", ", ".join(cv["langues"] or []) or "?"),
                ("Postes trouvés", len(cv["experiences"]) or "?"),
                ("Suivi", suivi(cv)),
            ] + [(f"Points · {k}", f"{v}") for k, v in ev["points"].items()])
            colonne.markdown(
                f'<div class="colonne-comp"><h4>{e(nom)}</h4>{anneau(ev["score"], p["moyen"])}{lignes}</div>',
                unsafe_allow_html=True)

# ---------------- Export ----------------
tableau = pd.DataFrame([{
    "Rang": rangs[cv["fichier"]], "Candidat": cv["nom"] or cv["fichier"], "Score": cv["evaluation"]["score"],
    "Critères obligatoires": cv["evaluation"]["statut"], "Suivi": suivi(cv), "Note du recruteur": note(cv),
    "Expérience (ans)": cv["annees_experience"], "Diplôme": cv["diplome"],
    "Langues": ", ".join(cv["langues"] or []), "Téléphone": cv["telephone"], "E-mail": cv["email"],
    "À vérifier": cv["a_verifier"], "Fichier": cv["fichier"],
} for cv in cvs])

with o_export:
    st.dataframe(tableau, hide_index=True, width="stretch",
                 column_config={"Score": st.column_config.ProgressColumn(
                     "Score", min_value=0, max_value=100, format="%d")})
    sortie = io.BytesIO()
    tableau.to_excel(sortie, index=False, sheet_name="Classement")
    st.download_button("⬇️ Télécharger le classement (Excel)", sortie.getvalue(), "preselection_cv.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

with o_methode:
    st.markdown("""
**Le score sur 100** suit vos réglages :

| Critère | Points |
|---|---|
| Expérience (tous les points à partir de l'expérience idéale) | 35 |
| Déjà en relation client (conseiller, téléconseiller, chargé de clientèle) | 20 |
| Compétences recherchées trouvées dans le CV | 25 |
| Anglais | 10 |
| Niveau d'études au moins égal au minimum | 10 |

Les candidats qui remplissent les **critères obligatoires** passent en tête, puis sont classés par score.

**Comment le CV est lu :** le texte est extrait (OCR pour les scans et les photos), nettoyé, puis un modèle
d'intelligence artificielle (spaCy) repère les postes, entreprises, dates, diplômes et compétences, et les relie entre eux.

**À savoir :** la lecture automatique peut se tromper, surtout sur un scan de mauvaise qualité. Les CV marqués
« À vérifier » doivent être relus. Les informations personnelles sans rapport avec le poste (date de naissance,
situation familiale, nationalité) sont retirées et n'entrent pas dans le score.
""")

bloc('<div class="pied">Projet de certification Data Science · Analyse de CV avec Python, OCR et spaCy</div>')