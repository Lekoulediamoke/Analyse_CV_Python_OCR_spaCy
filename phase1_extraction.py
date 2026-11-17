# ==============================================================
# PHASE 1 - Extraction des données des CV
# Projet : présélection automatisée de CV de conseillers clientèle
#
# Pour chaque CV du dossier cv_exemples/ (PDF, image ou Word) :
#   1. Extraction du texte : lecture directe, ou OCR (Tesseract) si le
#      document est une image ou un PDF scanné
#   2. Prétraitement du texte : nettoyage des caractères, puces, espaces
#   3. Extraction des informations : nom, e-mail, téléphone, formation,
#      expérience professionnelle, compétences, langues
#   4. Export : un fichier JSON par CV + un tableau CSV récapitulatif
#
# Usage : python phase1_extraction.py [dossier_des_cv]
# ==============================================================

import csv
import difflib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from datetime import date

import pdfplumber
import pytesseract
from docx import Document
from PIL import Image, ImageOps, ImageFilter

DOSSIER_CV = sys.argv[1] if len(sys.argv) > 1 else "cv_exemples"
DOSSIER_RESULTATS = "resultats"
ANNEE_COURANTE = date.today().year


# ==============================================================
# 1. EXTRACTION DU TEXTE
# ==============================================================
def configurer_tesseract():
    """Trouve Tesseract (sous Windows, il n'est pas toujours dans le PATH)."""
    if shutil.which("tesseract") is None:
        for chemin in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                       r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if os.path.exists(chemin):
                pytesseract.pytesseract.tesseract_cmd = chemin
                break
    try:
        langues = pytesseract.get_languages()
    except Exception:
        print("ERREUR : Tesseract est introuvable. Installez-le avant de lancer ce script.")
        sys.exit(1)
    # Le français reconnaît les accents ; l'anglais sert de secours
    langue = "+".join(l for l in ("fra", "eng") if l in langues) or "eng"
    if "fra" not in langues:
        print("Attention : la langue française de Tesseract n'est pas installée,")
        print("les accents risquent d'être mal reconnus.")
    return langue


def preparer_image(image):
    """Améliore une image avant l'OCR : gris, contraste, netteté, taille."""
    image = ImageOps.exif_transpose(image)          # photos de téléphone mal orientées
    image = image.convert("L")                       # niveaux de gris
    if image.width < 1500:                           # agrandir les petites images
        facteur = 1500 / image.width
        image = image.resize((int(image.width * facteur), int(image.height * facteur)))
    image = ImageOps.autocontrast(image)
    return image.filter(ImageFilter.SHARPEN)


def ocr(image, langue):
    """Lit le texte d'une image. Renvoie aussi la confiance moyenne de
    Tesseract (0-100) : une valeur basse signale un CV à vérifier à la main."""
    donnees = pytesseract.image_to_data(preparer_image(image), lang=langue,
                                        output_type=pytesseract.Output.DICT)
    lignes, confiances = {}, []
    for i, mot in enumerate(donnees["text"]):
        if not mot.strip():
            continue
        cle = (donnees["block_num"][i], donnees["par_num"][i], donnees["line_num"][i])
        lignes.setdefault(cle, []).append(mot)
        if float(donnees["conf"][i]) >= 0:
            confiances.append(float(donnees["conf"][i]))
    texte = "\n".join(" ".join(mots) for _, mots in sorted(lignes.items()))
    confiance = sum(confiances) / len(confiances) if confiances else 0
    return texte, confiance


def extraire_texte(chemin, langue):
    """Renvoie (texte, méthode utilisée, confiance OCR ou None)."""
    extension = os.path.splitext(chemin)[1].lower()

    if extension == ".pdf":
        pages, confiances = [], []
        methode = "texte PDF"
        with pdfplumber.open(chemin) as pdf:
            for page in pdf.pages:
                texte = page.extract_text() or ""
                if len(texte.strip()) < 50:          # page sans texte : c'est un scan
                    image = page.to_image(resolution=300).original
                    texte, confiance = ocr(image, langue)
                    confiances.append(confiance)
                    methode = "OCR (PDF scanné)"
                pages.append(texte)
        confiance = sum(confiances) / len(confiances) if confiances else None
        return "\n".join(pages), methode, confiance

    if extension in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        texte, confiance = ocr(Image.open(chemin), langue)
        return texte, "OCR (image)", confiance

    if extension == ".docx":
        document = Document(chemin)
        return "\n".join(p.text for p in document.paragraphs), "texte Word", None

    with open(chemin, encoding="utf-8", errors="ignore") as f:     # .txt
        return f.read(), "texte brut", None


# ==============================================================
# 2. PRÉTRAITEMENT DU TEXTE
# ==============================================================
PUCES = r"^\s*(?:[•●▪■◦○➢➤►✓✔\*·\-–—#]+|\.(?=\s))\s*"


def nettoyer_texte(texte):
    texte = unicodedata.normalize("NFKC", texte)          # unifie les caractères spéciaux
    texte = texte.replace("’", "'").replace("‘", "'").replace(" ", " ")
    texte = re.sub(r"\(cid:\d+\)", "•", texte)            # symboles de PDF non décodés (puces)
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)        # mots coupés en fin de ligne
    lignes = []
    for ligne in texte.splitlines():
        ligne = re.sub(PUCES, "- ", ligne)                # puces unifiées
        ligne = re.sub(r"[ \t]+", " ", ligne).strip()     # espaces multiples
        ligne = re.sub(r"(\s+[^\w\s(){}%]{1,2})+$", "", ligne)   # bruit d'OCR en fin de ligne
        ligne = ligne.strip("|_ '")
        if len(ligne) > 1 and ligne != "-":
            lignes.append(ligne)
    return "\n".join(lignes)


def normaliser(texte):
    """Minuscules sans accents ni ponctuation : sert aux comparaisons.
    Rend le script robuste aux accents perdus par l'OCR."""
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9' ]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


# ==============================================================
# 3. EXTRACTION DES INFORMATIONS
# ==============================================================
# --- Découpage en sections à partir des titres du CV ----------
TITRES_SECTIONS = {
    "profil": ["profil", "profil professionnel", "a propos", "a propos de moi", "resume",
               "objectif", "objectif professionnel", "summary", "profile"],
    "experience": ["experience", "experiences", "experience professionnelle",
                   "experiences professionnelles", "parcours professionnel",
                   "emplois", "work experience", "professional experience"],
    "formation": ["formation", "formations", "education", "parcours scolaire",
                  "parcours academique", "etudes", "diplomes", "diplomes et formations",
                  "cursus", "cursus scolaire", "formation academique"],
    "competences": ["competences", "competence", "competences cles",
                    "competences professionnelles", "savoir faire", "aptitudes",
                    "skills", "atouts", "qualites"],
    "langues": ["langues", "langue", "langues parlees", "languages"],
    "certifications": ["certifications", "certificats"],
    "interets": ["centres d'interet", "centre d'interet", "loisirs", "hobbies",
                 "activites extra professionnelles", "interets"],
    "references": ["references"],
}
TITRE_VERS_SECTION = {titre: section
                      for section, titres in TITRES_SECTIONS.items() for titre in titres}


def detecter_titre(ligne):
    """Renvoie le nom de la section si la ligne est un titre, sinon None.
    Tolère le bruit de l'OCR (« a PARCOURS PROFESSIONNEL », « EXPERlENCE »)."""
    mots = normaliser(ligne).split()
    if not mots or len(ligne) > 50:
        return None
    lettres = [c for c in ligne if c.isalpha()]
    majuscules = sum(c.isupper() for c in lettres) / len(lettres) if lettres else 0
    for depart in range(3):                         # ignore 0 à 2 petits « parasites » au début
        if depart and len(mots[depart - 1]) > 2:
            break
        restants = mots[depart:]
        for fin in range(len(restants), 0, -1):     # titre le plus long possible
            phrase = " ".join(restants[:fin])
            reste = " ".join(restants[fin:])
            if phrase not in TITRE_VERS_SECTION and len(phrase) >= 6:
                proche = difflib.get_close_matches(phrase, TITRE_VERS_SECTION, n=1, cutoff=0.88)
                phrase = proche[0] if proche else phrase
            if phrase in TITRE_VERS_SECTION:
                # Un titre est seul sur sa ligne, ou écrit en majuscules
                if not reste or (len(reste) <= 15 and majuscules >= 0.6):
                    return TITRE_VERS_SECTION[phrase]
    return None


def decouper_sections(texte):
    sections = {"en_tete": []}
    courante = "en_tete"
    for ligne in texte.splitlines():
        titre = detecter_titre(ligne)
        if titre:
            courante = titre
            sections.setdefault(courante, [])
        else:
            sections.setdefault(courante, []).append(ligne)
    return sections


# --- Coordonnées ----------------------------------------------
def extraire_email(texte, nom=None):
    """Renvoie (e-mail, reconstitué ?)."""
    texte = re.sub(r"\s*@\s*", "@", texte)               # l'OCR ajoute parfois des espaces
    trouve = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texte)
    if not trouve:
        return None, False
    email = trouve.group(0).lower().rstrip(".")
    # L'OCR perd parfois le point : « moussa fall@... » au lieu de « moussa.fall@... ».
    # Si le mot juste avant est une partie du nom du candidat, on le recolle.
    avant = re.search(r"([A-Za-z]+) $", texte[:trouve.start()])
    if nom and avant and normaliser(avant.group(1)) in normaliser(nom).split():
        return avant.group(1).lower() + "." + email, True
    return email, False


def extraire_telephone(texte):
    candidats = re.findall(r"(?:\+|00)?\d[\d .\-()]{7,}\d", texte)
    for candidat in candidats:
        if re.search(r"(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}", candidat):
            continue                                      # c'est une période, pas un numéro
        chiffres = re.sub(r"\D", "", candidat)
        if 9 <= len(chiffres) <= 13:
            return re.sub(r"\s+", " ", candidat).strip()
    return None


MOTS_PAS_UN_NOM = {"curriculum", "vitae", "cv", "conseiller", "conseillere", "agent",
                   "charge", "chargee", "teleconseiller", "teleconseillere", "commercial",
                   "assistant", "assistante", "responsable", "superviseur", "clientele",
                   "client", "recouvrement", "senegal", "dakar", "tel", "email", "adresse"}


def extraire_nom(lignes_en_tete):
    """Le nom est en général l'une des premières lignes : 2 à 4 mots,
    sans chiffre ni @, et qui n'est pas un intitulé de poste."""
    for ligne in lignes_en_tete[:6]:
        mots = ligne.replace("-", " ").split()
        if not 2 <= len(mots) <= 4:
            continue
        if re.search(r"[\d@|:]", ligne):
            continue
        if any(normaliser(m) in MOTS_PAS_UN_NOM for m in mots):
            continue
        if all(re.fullmatch(r"[A-Za-zÀ-ÿ'’]+", m) for m in mots):
            return " ".join(m.capitalize() if m.isupper() else m for m in mots)
    return None


def extraire_poste(lignes_en_tete, nom):
    """L'intitulé du poste suit généralement le nom."""
    for ligne in lignes_en_tete[:6]:
        ligne = re.sub(r"^(?:\S{1,2}\s+)+", "", ligne)   # bruit d'OCR en début de ligne
        if nom and normaliser(ligne) == normaliser(nom):
            continue
        if re.search(r"[\d@]", ligne):
            continue
        if any(mot in normaliser(ligne).split() for mot in MOTS_PAS_UN_NOM - {"senegal", "dakar"}):
            return ligne
    return None


# --- Listes (compétences, langues) ----------------------------
def decouper_elements(lignes):
    elements = []
    for ligne in lignes:
        ligne = re.sub(r"^- ", "", ligne)
        for morceau in re.split(r"[,;•|]", ligne):
            morceau = morceau.strip(" .-")
            if 1 < len(morceau) <= 60:
                elements.append(morceau)
    return elements


LANGUES_CONNUES = ["français", "anglais", "wolof", "espagnol", "arabe", "portugais",
                   "allemand", "italien", "pulaar", "peul", "sérère", "diola",
                   "mandingue", "soninké", "chinois", "russe"]


def extraire_langues(sections, texte):
    zone = " ".join(sections.get("langues", [])) or texte
    mots = normaliser(zone).split()
    trouvees = []
    for langue in LANGUES_CONNUES:
        # Tolère les fautes d'OCR : « Frangais » est reconnu comme « Français »
        if difflib.get_close_matches(normaliser(langue), mots, n=1, cutoff=0.85):
            trouvees.append(langue.capitalize())
    return trouvees


# Compétences clés du métier, recherchées dans tout le CV
COMPETENCES_METIER = {
    "Relation client": ["relation client", "service client", "relation clientele"],
    "Écoute active": ["ecoute active", "sens de l'ecoute", "ecoute"],
    "Gestion des réclamations": ["reclamation", "reclamations", "litiges"],
    "Appels entrants": ["appels entrants", "reception d'appels"],
    "Appels sortants": ["appels sortants", "emission d'appels", "phoning"],
    "Vente / vente additionnelle": ["vente additionnelle", "upselling", "vente", "ventes"],
    "Fidélisation": ["fidelisation"],
    "Recouvrement": ["recouvrement"],
    "Assistance technique": ["assistance technique", "support technique", "hotline"],
    "Multicanal (e-mail, chat)": ["chat", "e mail", "multicanal", "reseaux sociaux"],
    "Négociation": ["negociation", "negocier"],
    "Prospection": ["prospection", "prospecter"],
    "Outils CRM": ["crm", "salesforce", "zendesk", "freshdesk", "hubspot"],
    "Bureautique": ["pack office", "excel", "word", "bureautique", "outlook"],
    "Indicateurs (KPI)": ["dmt", "kpi", "indicateurs", "taux de resolution", "satisfaction"],
}


def extraire_competences_metier(texte):
    texte = " " + normaliser(texte) + " "
    trouvees = []
    if " apres vente " in texte or " sav " in texte:
        trouvees.append("Service après-vente")
        texte = texte.replace(" apres vente ", " ")       # « après-vente » n'est pas de la vente
    trouvees += [competence for competence, mots in COMPETENCES_METIER.items()
                 if any(f" {mot} " in texte for mot in mots)]
    return trouvees


# --- Formation ------------------------------------------------
NIVEAUX_DIPLOMES = [   # du plus élevé au plus bas
    ("Doctorat", ["doctorat", "phd"]),
    ("Master / Bac+5", ["master", "mba", "dess", "dea", "ingenieur", "bac 5"]),
    ("Licence / Bac+3", ["licence", "bachelor", "bac 3"]),
    ("Bac+2 (BTS, DUT…)", ["bts", "dut", "deug", "dts", "bac 2"]),
    ("Baccalauréat", ["baccalaureat", "bac"]),
    ("BFEM / Brevet", ["bfem", "brevet"]),
]


def diplome_le_plus_eleve(lignes_formation):
    zone = " " + normaliser(" ".join(lignes_formation)) + " "
    for niveau, mots in NIVEAUX_DIPLOMES:
        if any(f" {mot} " in zone for mot in mots):
            return niveau
    return None


# --- Expérience -----------------------------------------------
MOIS = {"janv": 1, "jan": 1, "fev": 2, "feb": 2, "mars": 3, "mar": 3, "avr": 4, "apr": 4,
        "mai": 5, "may": 5, "juin": 6, "jun": 6, "juil": 7, "jul": 7, "aout": 8, "aug": 8,
        "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MOTS_PRESENT = r"(?:present|aujourd'hui|aujourd hui|ce jour|actuel|actuellement|now|current)"


def periodes(texte):
    """Trouve les périodes du type « 2019 - 2022 », « mars 2022 - présent »."""
    texte = normaliser(texte)
    motif = (rf"(?:([a-z]+)\s+)?((?:19|20)\d{{2}})\s*(?:a|au|to)?\s*"
             rf"(?:(?:([a-z]+)\s+)?((?:19|20)\d{{2}})|{MOTS_PRESENT})")
    resultat = []
    for mois_debut, annee_debut, mois_fin, annee_fin in re.findall(motif, texte):
        debut = int(annee_debut) + (MOIS.get(mois_debut[:4], MOIS.get(mois_debut[:3], 1)) - 1) / 12
        if annee_fin:
            fin = int(annee_fin) + (MOIS.get(mois_fin[:4], MOIS.get(mois_fin[:3], 12)) - 1) / 12
        else:
            fin = ANNEE_COURANTE + (date.today().month - 1) / 12
        if 0 < fin - debut < 45:
            resultat.append((debut, fin))
    return resultat


def annees_experience(lignes_experience, texte_complet):
    # 1. Somme des périodes trouvées dans la section expérience
    total = sum(fin - debut for debut, fin in periodes(" ".join(lignes_experience)))
    # 2. Ou mention explicite : « 4 ans d'expérience »
    mentions = re.findall(r"(\d{1,2})\s*(?:ans|annees|years)\s+d\s?'?\s?experience",
                          normaliser(texte_complet))
    if mentions:
        total = max(total, max(int(m) for m in mentions))
    return round(total, 1) if total else None


# ==============================================================
# 4. ANALYSE D'UN CV ET EXPORT
# ==============================================================
def analyser_cv(chemin, langue):
    debut = time.time()
    texte_brut, methode, confiance = extraire_texte(chemin, langue)
    texte = nettoyer_texte(texte_brut)
    sections = decouper_sections(texte)
    en_tete = sections.get("en_tete", [])
    experience = sections.get("experience", [])
    formation = sections.get("formation", [])
    nom = extraire_nom(en_tete)
    email, email_reconstitue = extraire_email(texte, nom)
    # Compétences métier cherchées hors de l'en-tête (« E-mail : » n'est pas une compétence)
    corps = "\n".join(l for s, lignes in sections.items() if s != "en_tete" for l in lignes)

    infos = {
        "fichier": os.path.basename(chemin),
        "methode_extraction": methode,
        "confiance_ocr": round(confiance, 1) if confiance is not None else None,
        # Un OCR peu fiable ou un champ clé manquant : un humain doit vérifier
        "a_verifier": None,
        "nom": nom,
        "poste_vise": extraire_poste(en_tete, nom),
        "email": email,
        "telephone": extraire_telephone(texte),
        "formation": [re.sub(r"^- ", "", l) for l in formation],
        "diplome_le_plus_eleve": diplome_le_plus_eleve(formation),
        "experience": [re.sub(r"^- ", "", l) for l in experience],
        "annees_experience": annees_experience(experience, texte),
        "competences": decouper_elements(sections.get("competences", [])),
        "competences_metier": extraire_competences_metier(corps),
        "langues": extraire_langues(sections, texte),
        "sections_detectees": [s for s in sections if s != "en_tete"],
        "duree_traitement_s": round(time.time() - debut, 2),
    }
    manquants = [c for c in ("nom", "email", "telephone") if not infos[c]]
    raisons = [f"{c} non trouvé" for c in manquants]
    if email_reconstitue:
        raisons.append("e-mail reconstitué après l'OCR")
    if confiance is not None and confiance < 80:
        raisons.append(f"OCR peu fiable ({confiance:.0f}/100)")
    infos["a_verifier"] = " ; ".join(raisons) or "non"
    return texte, infos


def main():
    langue = configurer_tesseract()
    os.makedirs(os.path.join(DOSSIER_RESULTATS, "textes"), exist_ok=True)
    os.makedirs(os.path.join(DOSSIER_RESULTATS, "json"), exist_ok=True)
    print(f"Langue(s) OCR : {langue}")
    print(f"Analyse des CV du dossier « {DOSSIER_CV} »\n")

    resultats = []
    for nom_fichier in sorted(os.listdir(DOSSIER_CV)):
        chemin = os.path.join(DOSSIER_CV, nom_fichier)
        if nom_fichier.startswith((".", "_", "~$")) or not os.path.isfile(chemin):
            continue
        if os.path.splitext(nom_fichier)[1].lower() not in (
                ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".docx", ".txt"):
            print(f"  [ignoré] {nom_fichier} : format non pris en charge")
            continue
        try:
            texte, infos = analyser_cv(chemin, langue)
        except Exception as erreur:
            print(f"  [erreur] {nom_fichier} : {erreur}")
            continue
        resultats.append(infos)
        base = os.path.splitext(nom_fichier)[0]
        with open(os.path.join(DOSSIER_RESULTATS, "textes", base + ".txt"), "w", encoding="utf-8") as f:
            f.write(texte)
        with open(os.path.join(DOSSIER_RESULTATS, "json", base + ".json"), "w", encoding="utf-8") as f:
            json.dump(infos, f, ensure_ascii=False, indent=2)
        print(f"  [ok] {nom_fichier:<28} {infos['methode_extraction']:<18} "
              f"{infos['duree_traitement_s']:>5.1f} s  ->  {infos['nom']}"
              + ("" if infos["a_verifier"] == "non" else f"   (à vérifier : {infos['a_verifier']})"))

    # Tableau récapitulatif (ouvrable dans Excel)
    colonnes = ["fichier", "methode_extraction", "confiance_ocr", "a_verifier", "nom", "poste_vise", "email", "telephone",
                "diplome_le_plus_eleve", "annees_experience", "langues",
                "competences_metier", "competences", "formation", "experience"]
    chemin_csv = os.path.join(DOSSIER_RESULTATS, "cv_extraits.csv")
    with open(chemin_csv, "w", newline="", encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=colonnes, delimiter=";", extrasaction="ignore")
        ecrivain.writeheader()
        for infos in resultats:
            ligne = {c: " | ".join(map(str, v)) if isinstance(v, list) else v
                     for c, v in infos.items()}
            ecrivain.writerow(ligne)
    with open(os.path.join(DOSSIER_RESULTATS, "cv_extraits.json"), "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

    # Bilan : taux de remplissage de chaque champ
    print(f"\n=== Bilan : {len(resultats)} CV analysés ===")
    champs = ["nom", "email", "telephone", "diplome_le_plus_eleve", "annees_experience",
              "competences", "langues"]
    for champ in champs:
        remplis = sum(1 for r in resultats if r[champ])
        print(f"  {champ:<24} trouvé dans {remplis}/{len(resultats)} CV")
    print(f"\nRésultats enregistrés dans le dossier « {DOSSIER_RESULTATS} » :")
    print("  - cv_extraits.csv  (tableau récapitulatif, s'ouvre dans Excel)")
    print("  - cv_extraits.json (toutes les informations)")
    print("  - json/  et  textes/  (détail et texte extrait de chaque CV)")

    # Aperçu détaillé du premier CV
    if resultats:
        print("\n=== Exemple de résultat ===")
        print(json.dumps(resultats[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
