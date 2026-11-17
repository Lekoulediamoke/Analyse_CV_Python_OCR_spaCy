# ==============================================================
# PHASE 2 - Nettoyage et normalisation des données
# Projet : Analyse de CV en apprentissage automatique avec Python, OCR et spaCy
#
# Entrée  : les résultats de la phase 1 (resultats/cv_extraits.json
#           et le texte de chaque CV dans resultats/textes/)
# Trois parties, comme dans les instructions :
#   A. Supprimer le bruit et les informations non pertinentes du texte
#      (expressions régulières, manipulation de chaînes)
#   B. Corriger les incohérences de formatage des champs
#      (dates avec dateutil, téléphones, e-mails, noms, fautes d'OCR…)
#   C. Normaliser le texte : tokenisation, mots vides,
#      racinisation (NLTK) et lemmatisation (spaCy)
# Sorties : resultats/cv_nettoyes.json et .csv, resultats/textes_nettoyes/,
#           resultats/journal_nettoyage.csv (chaque correction : avant -> après)
#
# Usage : python phase2_nettoyage.py [dossier_de_resultats]
#         (ex. : python phase2_nettoyage.py resultats_cv_reels)
# ==============================================================

import csv
import difflib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

DOSSIER = sys.argv[1] if len(sys.argv) > 1 else "resultats"
AUJOURD_HUI = date.today()
journal = []          # toutes les corrections, pour le rapport


def noter(fichier, champ, avant, apres, regle):
    """Enregistre une correction dans le journal (avant -> après)."""
    if avant != apres:
        journal.append({"fichier": fichier, "champ": champ, "avant": str(avant),
                        "apres": str(apres), "regle": regle})


def sans_accents(texte):
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


def cle(texte):
    """Forme simplifiée pour comparer deux textes : minuscules, sans accents."""
    return re.sub(r"[^a-z0-9]+", " ", sans_accents(texte.lower())).strip()


# ==============================================================
# A. BRUIT ET INFORMATIONS NON PERTINENTES (texte complet)
# ==============================================================
# Informations personnelles inutiles pour juger une candidature, et qui
# peuvent créer des discriminations : on les retire du texte.
INFOS_PERSONNELLES = re.compile(
    r"\b(n[ée]e?\s+le|date\s+de\s+naissance|[âa]ge\s*:|\d{2}\s*ans\b(?!\s+d)|"
    r"mari[ée]e?|c[ée]libataire|divorc[ée]e?|veu(?:f|ve)|situation\s+(?:familiale|matrimoniale)|"
    r"nationalit[ée]|religion|permis\s+[a-z]\b)", re.IGNORECASE)

# Lignes sans intérêt : numéros de page, mentions « CV »
LIGNES_INUTILES = re.compile(
    r"^\s*(page\s*\d+\s*(?:/|sur)\s*\d+|curriculum\s+vitae|cv)\s*$", re.IGNORECASE)

# Sections non pertinentes pour la présélection
SECTIONS_A_RETIRER = {"centres d interet", "centre d interet", "loisirs", "hobbies",
                      "interets", "references", "activites extra professionnelles"}
TITRES_CONNUS = {"profil", "experience", "experiences", "experience professionnelle",
                 "experiences professionnelles", "parcours professionnel", "formation",
                 "formations", "education", "parcours scolaire", "competences",
                 "savoir faire", "langues", "certifications"} | SECTIONS_A_RETIRER

MOTS_COURTS_FRANCAIS = {"a", "à", "au", "de", "du", "en", "et", "la", "le", "un", "l", "d", "y"}


def nettoyer_ligne(ligne):
    """Retire le bruit d'une ligne avec des expressions régulières."""
    ligne = re.sub(r"[‘’`´]", "'", ligne)                       # apostrophes unifiées
    ligne = re.sub(r"[|_~#*¥©®]+", " ", ligne)                    # symboles parasites d'OCR
    # Titre de section entouré de bruit : « a PARCOURS PROFESSIONNEL », « SAVOIR-FAIRE eek Set! »
    titre = re.search(r"[A-ZÀ-Ý][A-ZÀ-Ý' -]{3,}[A-ZÀ-Ý]", ligne)
    if titre and titre.start() <= 2 and cle(titre.group(0)) in TITRES_CONNUS:
        return titre.group(0).strip()
    ligne = re.sub(r"(\w)-\s*-?\s*(\w)", r"\1-\2", ligne)        # « apres- -vente » -> « apres-vente »
    ligne = re.sub(r"\.(\s+[a-zà-ÿ])", r"\1", ligne)              # point au milieu d'une phrase
    ligne = re.sub(r"\s+([.,)])", r"\1", ligne)                   # pas d'espace avant . , )
    ligne = re.sub(r"\s*([:;])\s*", r" \1 ", ligne)               # « : » et « ; » à la française
    ligne = re.sub(r"\{", "(", ligne)                            # « {2019 » -> « (2019 »
    # Petits morceaux parasites en début de ligne (« sd », « 2 »), sauf vrais mots
    mots = ligne.split()
    while mots and len(mots[0]) <= 2 and mots[0].lower() not in MOTS_COURTS_FRANCAIS \
            and not re.fullmatch(r"\d{2}/\d{4}", mots[0]):
        mots.pop(0)
    ligne = " ".join(mots)
    ligne = re.sub(r"[\s.,;:\-]+$", "", ligne)                   # ponctuation finale isolée
    ligne = re.sub(r"\s+[a-z]$", "", ligne)                       # lettre minuscule isolée à la fin
    return ligne.strip()


def proportion_lettres(ligne):
    return sum(c.isalpha() for c in ligne) / max(len(ligne), 1)


def nettoyer_texte(texte, fichier):
    lignes_gardees = []
    section_ignoree = False
    for ligne in texte.splitlines():
        brut = ligne
        titre = cle(ligne)
        if titre in TITRES_CONNUS:
            section_ignoree = titre in SECTIONS_A_RETIRER
            if section_ignoree:
                noter(fichier, "texte", brut, "", "section non pertinente retirée")
                continue
        if section_ignoree:
            noter(fichier, "texte", brut, "", "section non pertinente retirée")
            continue
        if LIGNES_INUTILES.match(ligne):
            noter(fichier, "texte", brut, "", "ligne inutile (page, « CV »)")
            continue
        if INFOS_PERSONNELLES.search(ligne):
            noter(fichier, "texte", brut, "", "information personnelle retirée")
            continue
        ligne = nettoyer_ligne(ligne)
        coordonnees = "@" in ligne or len(re.sub(r"\D", "", ligne)) >= 8
        if len(ligne) < 3 or (proportion_lettres(ligne) < 0.4 and not coordonnees):
            noter(fichier, "texte", brut, "", "ligne de bruit")
            continue
        noter(fichier, "texte", brut, ligne, "nettoyage regex")
        lignes_gardees.append(ligne)
    return "\n".join(lignes_gardees)


# ==============================================================
# B. INCOHÉRENCES DE FORMATAGE (champs extraits)
# ==============================================================
# --- Fautes d'OCR et accents manquants : vocabulaire du domaine -------
VOCABULAIRE = [
    "clientèle", "conseiller", "conseillère", "téléconseiller", "téléconseillère",
    "chargé", "chargée", "téléopérateur", "baccalauréat", "université", "expérience",
    "réclamations", "négociation", "prospection", "communication", "entreprise",
    "résolution", "satisfaction", "télécom", "assistance", "technique", "après",
    "gestion", "commercialisation", "recouvrement", "fidélisation", "accueil",
    "orientation", "professionnels", "portefeuille", "indicateurs", "téléphoniques",
    "échéanciers", "opérateur", "français", "Sénégal", "Thiès", "porte",
]
VOCAB_CLES = {cle(m): m for m in VOCABULAIRE}


def corriger_mots(texte, fichier, champ):
    """Remplace chaque mot mal reconnu par le mot du vocabulaire le plus proche.
    Ex. : « clientéle » -> « clientèle », « Baccalaursat » -> « Baccalauréat »."""
    def remplacer(trouve):
        mot = trouve.group(0)
        if len(mot) < 5 or mot in VOCABULAIRE:
            return mot
        k = cle(mot)
        bon = VOCAB_CLES.get(k)                                 # même mot, accents différents
        if bon is None:
            proche = difflib.get_close_matches(k, VOCAB_CLES, n=1, cutoff=0.85)
            # Pas de correction entre singulier et pluriel, masculin et féminin
            # (« entreprises », « professionnelles » sont de vrais mots)
            if proche and abs(len(proche[0]) - len(k)) <= 1 \
                    and not proche[0].startswith(k) and not k.startswith(proche[0]):
                bon = VOCAB_CLES[proche[0]]
        if bon is None or bon == mot:
            return mot
        if mot.isupper():                                       # garder la casse d'origine
            bon = bon.upper()
        elif mot[0].isupper():
            bon = bon[0].upper() + bon[1:]
        if bon == mot:
            return mot
        noter(fichier, champ, mot, bon, "correction d'un mot mal reconnu (OCR)")
        return bon
    return re.sub(r"[A-Za-zÀ-ÿ]+", remplacer, texte)


# --- Identité et coordonnées ------------------------------------------
def normaliser_nom(nom):
    if not nom:
        return None
    nom = re.sub(r"[^A-Za-zÀ-ÿ' -]", "", nom)
    return " ".join("-".join(p.capitalize() for p in mot.split("-")) for mot in nom.split())


def normaliser_email(email):
    if not email:
        return None, False
    email = email.strip().lower().replace(" ", "")
    valide = re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", email)
    return email, bool(valide)


def normaliser_telephone(tel):
    """Format international unique : +221 77 512 34 56 (Sénégal), +33 6 12 34 56 78 (France)."""
    if not tel:
        return None, False
    chiffres = re.sub(r"\D", "", tel)
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    if len(chiffres) == 9 and chiffres[0] in "37":              # numéro sénégalais sans indicatif
        chiffres = "221" + chiffres
    if len(chiffres) == 10 and chiffres.startswith("0"):        # numéro français sans indicatif
        chiffres = "33" + chiffres[1:]
    if len(chiffres) == 12 and chiffres.startswith("221"):
        n = chiffres[3:]
        return f"+221 {n[:2]} {n[2:5]} {n[5:7]} {n[7:]}", True
    if len(chiffres) == 11 and chiffres.startswith("33"):
        n = chiffres[2:]
        return "+33 " + n[0] + " " + " ".join(n[i:i + 2] for i in range(1, 9, 2)), True
    return "+" + chiffres, False


# --- Poste visé : une catégorie standard ------------------------------
CATEGORIES_POSTE = [
    ("Conseiller clientèle", ["conseiller client", "conseillere client"]),
    ("Téléconseiller", ["teleconseill", "teleoperat", "televendeu"]),
    ("Chargé de clientèle", ["charge de client", "chargee de client"]),
    ("Agent de recouvrement", ["recouvrement"]),
    ("Commercial", ["commercial", "vendeu"]),
    ("Agent d'accueil", ["accueil"]),
]


def categorie_poste(poste):
    if not poste:
        return None
    k = cle(poste)
    for categorie, motifs in CATEGORIES_POSTE:
        if any(m in k for m in motifs):
            return categorie
    return "Autre"


# --- Dates : formats variés -> AAAA-MM avec dateutil ------------------
class MoisFrancais(date_parser.parserinfo):
    """Apprend à dateutil les noms de mois en français."""
    MONTHS = [("janv", "janvier", "jan"), ("fevr", "fevrier", "fev", "févr", "février"),
              ("mars",), ("avr", "avril"), ("mai",), ("juin",), ("juil", "juillet"),
              ("aout", "août"), ("sept", "septembre"), ("oct", "octobre"),
              ("nov", "novembre"), ("dec", "decembre", "déc", "décembre")]


MOIS_FR = r"(?:janv\w*|f[ée]v\w*|mars|avr\w*|mai|juin|juil\w*|ao[uû]t|sept\w*|oct\w*|nov\w*|d[ée]c\w*)\.?"
UNE_DATE = rf"(?:{MOIS_FR}\s+(?:19|20)\d{{2}}|\d{{1,2}}/(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
MAINTENANT = r"(?:pr[ée]sent|aujourd'hui|ce\s+jour|actuel(?:lement)?|en\s+cours)"
PERIODE = re.compile(
    rf"(?:depuis\s+(?P<depuis>{UNE_DATE}))|"
    rf"(?P<debut>{UNE_DATE})\s*(?:-|–|—|à|au|a)\s*(?P<fin>{UNE_DATE}|{MAINTENANT})",
    re.IGNORECASE)


def lire_date(texte, fin_de_periode=False):
    """« Mars 2022 », « 03/2019 » ou « 2023 » -> date. Une année seule
    compte comme janvier en début de période, décembre en fin de période."""
    if re.fullmatch(MAINTENANT, texte, re.IGNORECASE):
        return AUJOURD_HUI.replace(day=1)
    par_defaut = datetime(1900, 12 if fin_de_periode else 1, 1)
    return date_parser.parse(texte, parserinfo=MoisFrancais(dayfirst=True),
                             default=par_defaut).date()


def extraire_periodes(lignes, fichier):
    periodes = []
    for ligne in lignes:
        for m in PERIODE.finditer(ligne):
            if m.group("depuis"):
                debut, fin = lire_date(m.group("depuis")), AUJOURD_HUI.replace(day=1)
            else:
                debut = lire_date(m.group("debut"))
                fin = lire_date(m.group("fin"), fin_de_periode=True)
            if fin < debut:
                noter(fichier, "periode", m.group(0), "", "période incohérente ignorée")
                continue
            texte_norm = f"{debut:%Y-%m} -> {fin:%Y-%m}"
            noter(fichier, "periode", m.group(0), texte_norm, "date normalisée (dateutil)")
            periodes.append((debut, fin))
    return periodes


def duree_totale_annees(periodes):
    """Additionne les périodes en fusionnant celles qui se chevauchent
    (deux emplois en même temps ne comptent pas double)."""
    fusion = []
    for debut, fin in sorted(periodes):
        if fusion and debut <= fusion[-1][1]:
            fusion[-1][1] = max(fusion[-1][1], fin)
        else:
            fusion.append([debut, fin])
    mois = 0
    for debut, fin in fusion:
        ecart = relativedelta(fin, debut)
        mois += ecart.years * 12 + ecart.months + 1           # mois de fin inclus
    return round(mois / 12, 1)


# --- Formation : niveau en années après le bac ------------------------
NIVEAUX = {"Doctorat": 8, "Master / Bac+5": 5, "Licence / Bac+3": 3,
           "Bac+2 (BTS, DUT…)": 2, "Baccalauréat": 0, "BFEM / Brevet": -1}


# --- Compétences : doublons, casse, synonymes -------------------------
SYNONYMES = {"crm": "CRM", "excel": "Excel", "word": "Word", "pack office": "Pack Office",
             "salesforce": "Salesforce", "zendesk": "Zendesk", "powerpoint": "PowerPoint",
             "ecoute active": "Écoute active", "relation clientele": "Relation client",
             "service client": "Relation client"}


def normaliser_competences(liste, fichier):
    resultat, vues = [], set()
    for brut in liste:
        for morceau in re.split(r"\s*[:;,/]\s*", brut):
            morceau = nettoyer_ligne(morceau)
            k = cle(morceau)
            if len(k) < 2 or len(morceau) > 40 or not re.search(r"[A-Za-zÀ-ÿ]{2}", morceau):
                continue
            propre = SYNONYMES.get(k, morceau[0].upper() + morceau[1:])
            if cle(propre) in vues:
                noter(fichier, "competences", brut, "", "doublon retiré")
                continue
            vues.add(cle(propre))
            noter(fichier, "competences", morceau, propre, "casse / synonyme unifiés")
            resultat.append(propre)
    return resultat


# ==============================================================
# C. NORMALISATION LINGUISTIQUE : tokenisation, racines, lemmes
# ==============================================================
def charger_outils_nlp():
    """spaCy (tokenisation, mots vides, lemmes) et NLTK (racinisation)."""
    nlp = racineur = None
    try:
        import spacy
        nlp = spacy.load("fr_core_news_sm")
    except Exception:
        print("  spaCy ou son modèle français est absent : lemmatisation ignorée.")
        print("  -> python -m pip install spacy  puis  python -m spacy download fr_core_news_sm")
    try:
        from nltk.stem.snowball import FrenchStemmer
        racineur = FrenchStemmer()
    except Exception:
        print("  NLTK est absent : racinisation ignorée.  -> python -m pip install nltk")
    return nlp, racineur


def tokeniser(texte, nlp):
    """Découpe en mots (tokens). Avec spaCy : gère « l'appel », « e-mail »…"""
    if nlp:
        return [t for t in nlp(texte)]
    return re.findall(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)*", texte)


def normaliser_texte_nlp(texte, nlp, racineur):
    """Renvoie (lemmes, racines) des mots utiles : sans mots vides,
    ponctuation ni chiffres. Sert à comparer les CV à une offre d'emploi."""
    lemmes, racines = [], []
    for token in tokeniser(texte, nlp):
        mot = token.text if nlp else token
        if nlp and (token.is_stop or token.is_punct or token.like_num or token.is_space):
            continue
        if len(mot) < 3 or not mot.isalpha():
            continue
        if nlp:
            lemmes.append(token.lemma_.lower())
        if racineur:
            racines.append(racineur.stem(mot.lower()))
    return sorted(set(lemmes)), sorted(set(racines))


def demonstration_nlp(nlp, racineur):
    phrase = "Traitement des réclamations et gestion des appels entrants pour les clients professionnels"
    print(f"\n=== C. Normalisation linguistique : exemple ===\n« {phrase} »\n")
    print(f"  {'Token':<16}{'Mot vide ?':<12}{'Racine (NLTK)':<16}{'Lemme (spaCy)'}")
    lignes = []
    for token in tokeniser(phrase, nlp):
        mot = token.text if nlp else token
        vide = (token.is_stop if nlp else "?")
        racine = racineur.stem(mot.lower()) if racineur else "-"
        lemme = token.lemma_ if nlp else "-"
        print(f"  {mot:<16}{str(vide):<12}{racine:<16}{lemme}")
        lignes.append({"token": mot, "mot_vide": vide, "racine": racine, "lemme": lemme})
    with open(os.path.join(DOSSIER, "exemple_normalisation.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=lignes[0].keys(), delimiter=";")
        ecrivain.writeheader()
        ecrivain.writerows(lignes)


# ==============================================================
# TRAITEMENT D'UN CV ET PROGRAMME PRINCIPAL
# ==============================================================
def nettoyer_cv(cv, nlp, racineur):
    f = cv["fichier"]
    base = os.path.splitext(f)[0]

    # A. Texte complet
    chemin_texte = os.path.join(DOSSIER, "textes", base + ".txt")
    texte = open(chemin_texte, encoding="utf-8").read() if os.path.exists(chemin_texte) else ""
    texte_propre = corriger_mots(nettoyer_texte(texte, f), f, "texte")
    with open(os.path.join(DOSSIER, "textes_nettoyes", base + ".txt"), "w", encoding="utf-8") as sortie:
        sortie.write(texte_propre)

    # B. Champs
    nom = normaliser_nom(cv["nom"])
    noter(f, "nom", cv["nom"], nom, "casse unifiée")
    email, email_ok = normaliser_email(cv["email"])
    noter(f, "email", cv["email"], email, "e-mail en minuscules")
    tel, tel_ok = normaliser_telephone(cv["telephone"])
    noter(f, "telephone", cv["telephone"], tel, "format international")
    poste = corriger_mots(cv["poste_vise"] or "", f, "poste_vise") or None
    formation = [corriger_mots(nettoyer_ligne(l), f, "formation") for l in cv["formation"]]
    experience = [corriger_mots(nettoyer_ligne(l), f, "experience") for l in cv["experience"]]
    experience = [l for l in experience if len(l) >= 3]

    periodes = extraire_periodes(experience, f)
    annees = duree_totale_annees(periodes) if periodes else cv["annees_experience"]
    noter(f, "annees_experience", cv["annees_experience"], annees,
          "recalculée : dates normalisées, chevauchements fusionnés")

    # Contrôles de cohérence
    alertes = [] if cv["a_verifier"] == "non" else [cv["a_verifier"]]
    if email and not email_ok:
        alertes.append("e-mail invalide")
    if tel and not tel_ok:
        alertes.append("téléphone au format inconnu")
    if annees is not None and annees > 45:
        alertes.append("expérience incohérente")
        annees = None

    lemmes, racines = normaliser_texte_nlp(texte_propre, nlp, racineur)

    # Champs techniques de la phase 1 (méthode, durée, sections) non conservés
    return {
        "fichier": f,
        "nom": nom,
        "email": email,
        "telephone": tel,
        "poste_vise": poste,
        "categorie_poste": categorie_poste(poste),
        "diplome": cv["diplome_le_plus_eleve"],
        "niveau_bac_plus": NIVEAUX.get(cv["diplome_le_plus_eleve"]),
        "formation": formation,
        "experience": experience,
        "periodes": [f"{d:%Y-%m} -> {fn:%Y-%m}" for d, fn in sorted(periodes)],
        "annees_experience": annees,
        "competences": normaliser_competences(cv["competences"], f),
        "competences_cles": cv["competences_metier"],
        "langues": sorted(set(cv["langues"])),
        "lemmes": lemmes,
        "racines": racines,
        "a_verifier": " ; ".join(alertes) or "non",
    }


def retirer_doublons(cvs):
    """Un même candidat peut envoyer son CV deux fois (PDF et Word)."""
    gardes, vus = [], {}
    for cv in cvs:
        cles = [c for c in (cv["email"], cv["telephone"]) if c]
        doublon = next((vus[c] for c in cles if c in vus), None)
        if doublon:
            noter(cv["fichier"], "candidat", cv["fichier"], "", f"doublon de {doublon}")
            continue
        for c in cles:
            vus[c] = cv["fichier"]
        gardes.append(cv)
    return gardes


def main():
    entree = os.path.join(DOSSIER, "cv_extraits.json")
    if not os.path.exists(entree):
        print("Lancez d'abord la phase 1 : python phase1_extraction.py")
        return
    with open(entree, encoding="utf-8") as fichier:
        cvs = json.load(fichier)
    os.makedirs(os.path.join(DOSSIER, "textes_nettoyes"), exist_ok=True)

    print(f"=== Phase 2 : nettoyage de {len(cvs)} CV ===")
    nlp, racineur = charger_outils_nlp()
    propres = retirer_doublons([nettoyer_cv(cv, nlp, racineur) for cv in cvs])

    # Exports
    with open(os.path.join(DOSSIER, "cv_nettoyes.json"), "w", encoding="utf-8") as f:
        json.dump(propres, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DOSSIER, "cv_nettoyes.csv"), "w", newline="", encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=propres[0].keys(), delimiter=";")
        ecrivain.writeheader()
        for cv in propres:
            ecrivain.writerow({k: " | ".join(map(str, v)) if isinstance(v, list) else v
                               for k, v in cv.items()})
    with open(os.path.join(DOSSIER, "journal_nettoyage.csv"), "w", newline="", encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=["fichier", "champ", "regle", "avant", "apres"],
                                  delimiter=";")
        ecrivain.writeheader()
        ecrivain.writerows(journal)

    # Bilan
    print(f"\n=== Bilan : {len(journal)} corrections ===")
    par_regle = {}
    for entree_journal in journal:
        par_regle[entree_journal["regle"]] = par_regle.get(entree_journal["regle"], 0) + 1
    for regle, nombre in sorted(par_regle.items(), key=lambda x: -x[1]):
        print(f"  {nombre:>4}  {regle}")

    print("\n=== Exemples de corrections ===")
    exemples, compte = [], {}
    for j in journal:                                  # 3 exemples par type de correction
        if j["regle"] != "nettoyage regex" and compte.get(j["regle"], 0) < 3:
            compte[j["regle"]] = compte.get(j["regle"], 0) + 1
            exemples.append(j)
    for j in sorted(exemples, key=lambda j: j["regle"]):
        apres = j["apres"] if j["apres"] else "(supprimé)"
        print(f"  {j['regle'][:34]:<34} {j['avant'][:38]:<38} -> {apres[:30]}")

    print("\n=== Fiches nettoyées ===")
    for cv in propres:
        print(f"  {cv['nom']:<16} {cv['categorie_poste'] or '':<22} {cv['telephone'] or '':<19} "
              f"bac+{cv['niveau_bac_plus']}  {cv['annees_experience']} ans  "
              f"{', '.join(cv['langues'])}")

    demonstration_nlp(nlp, racineur)
    print(f"\nRésultats : {DOSSIER}/cv_nettoyes.csv, cv_nettoyes.json, journal_nettoyage.csv,")
    print(f"            exemple_normalisation.csv et textes_nettoyes/")


if __name__ == "__main__":
    main()
