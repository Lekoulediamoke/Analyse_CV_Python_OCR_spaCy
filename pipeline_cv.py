# ==============================================================
# Chaîne complète pour un lot de CV, utilisée par l'application web (app.py)
#
#   Phase 1 : lecture et OCR          -> phase1_extraction.analyser_cv
#   Phase 2 : nettoyage               -> phase2_nettoyage.nettoyer_cv
#   Phase 3 : entités (modèle spaCy)  -> modele_ner + règles
#   Phase 4 : relations               -> technique « Proximité + mise en page »
#   Score   : grille de critères réglée par le recruteur (transparente)
#
# Les fichiers sont traités dans un dossier temporaire, supprimé ensuite :
# aucun CV n'est conservé.
# ==============================================================

import os
import shutil
import tempfile

import phase1_extraction as p1
import phase2_nettoyage as p2
from phase4_relations import METHODES, preparer

TECHNIQUE_RELATIONS = "Proximité + mise en page"
FORMATS = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".docx", ".txt")
NIVEAU = "Niveau d'études"
POSTES_RELATION_CLIENT = ("Conseiller clientèle", "Téléconseiller", "Chargé de clientèle")
NIVEAUX = {"Aucun minimum": -9, "Baccalauréat": 0, "Bac+2 (BTS, DUT…)": 2,
           "Licence / Bac+3": 3, "Master / Bac+5": 5}


# --------------------------------------------------------------
# Outils : OCR et modèle d'entités
# --------------------------------------------------------------
def langue_ocr():
    """Langue(s) de Tesseract, ou None s'il n'est pas installé."""
    try:
        return p1.configurer_tesseract()
    except SystemExit:
        return None


def preparer_modele_ner():
    """Charge le modèle de la phase 3, ou l'entraîne s'il est absent (cas d'un
    serveur en ligne : quelques minutes, une seule fois). None en cas d'échec."""
    try:
        import spacy
        from spacy.training import Example
        import phase3_ner as p3
    except Exception:
        return None
    if os.path.isdir(p3.DOSSIER_MODELE):
        try:
            return p3.ajouter_regles(spacy.load(p3.DOSSIER_MODELE))
        except Exception:
            pass                       # modèle d'une autre version de spaCy : on le refait
    try:
        if not os.path.exists(p3.FICHIER_ANNOTE):
            import generer_donnees_annotees
            generer_donnees_annotees.main()
        donnees, _ = p3.charger_annotations(p3.FICHIER_ANNOTE)
        train_brut, test_brut = p3.separer(donnees)
        base = spacy.blank("fr")
        train, _, _ = p3.vers_exemples(base, train_brut, Example)
        test, _, _ = p3.vers_exemples(base, test_brut, Example)
        etiquettes = sorted({e[2] for _, entites, _ in donnees for e in entites})
        nlp, _ = p3.entrainer(spacy, train, test, etiquettes)
        nlp.to_disk(p3.DOSSIER_MODELE)
        return p3.ajouter_regles(nlp)
    except Exception:
        return None


# --------------------------------------------------------------
# Analyse d'un lot de CV
# --------------------------------------------------------------
def fiche(texte, nlp_ner):
    """Expériences et formations reliées (phases 3 et 4)."""
    entites = [{"start": e.start_char, "end": e.end_char, "label": e.label_, "text": e.text}
               for e in nlp_ner(texte).ents]
    preparer(texte, entites)
    liens = {}
    for type_rel, tete, queue in METHODES[TECHNIQUE_RELATIONS](texte, entites, None):
        liens.setdefault((tete, type_rel), []).append(queue)
    textes = {(e["start"], e["end"]): e["text"] for e in entites}
    lies = lambda e, t: [textes[q] for q in liens.get(((e["start"], e["end"]), t), [])]
    experiences = [{"Poste": e["text"], "Entreprise": ", ".join(lies(e, "EMPLOYEUR")),
                    "Période": " - ".join(lies(e, "PERIODE"))}
                   for e in entites if e["label"] == "POSTE" and not e["en_tete"]
                   and len(e["text"].split()) <= 6]          # contrôle qualité de la phase 5
    formations = [{"Diplôme": e["text"], "Établissement": ", ".join(lies(e, "ECOLE")),
                   "Année": " ".join(lies(e, "OBTENU_EN"))}
                  for e in entites if e["label"] == "DIPLOME"]
    return experiences, formations


def analyser_fichiers(chemins, langue, nlp_ner=None):
    """Renvoie (CV analysés, erreurs, nombre de doublons retirés)."""
    dossier = tempfile.mkdtemp(prefix="cv_")
    p2.DOSSIER = dossier
    p2.journal.clear()
    os.makedirs(os.path.join(dossier, "textes"))
    os.makedirs(os.path.join(dossier, "textes_nettoyes"))
    cvs, erreurs = [], []
    try:
        for chemin in chemins:
            nom = os.path.basename(chemin)
            if nom.startswith(("~$", ".")):
                continue          # fichier temporaire de Word (document ouvert) ou caché
            if os.path.splitext(nom)[1].lower() not in FORMATS:
                erreurs.append((nom, "format non pris en charge"))
                continue
            try:
                texte, infos = p1.analyser_cv(chemin, langue)
            except Exception as erreur:
                erreurs.append((nom, f"lecture impossible ({erreur})"))
                continue
            if not texte.strip():
                erreurs.append((nom, "aucun texte trouvé"))
                continue
            base = os.path.splitext(nom)[0]
            with open(os.path.join(dossier, "textes", base + ".txt"), "w", encoding="utf-8") as f:
                f.write(texte)
            cvs.append(infos)
        propres = [p2.nettoyer_cv(cv, None, None) for cv in cvs]
        uniques = p2.retirer_doublons(propres)
        for cv in uniques:
            base = os.path.splitext(cv["fichier"])[0]
            with open(os.path.join(dossier, "textes_nettoyes", base + ".txt"), encoding="utf-8") as f:
                texte = f.read()
            cv["experiences"], cv["formations"] = fiche(texte, nlp_ner) if nlp_ner else ([], [])
            for cle in ("lemmes", "racines"):
                cv.pop(cle, None)
        return uniques, erreurs, len(propres) - len(uniques)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)       # aucun CV n'est conservé


# --------------------------------------------------------------
# Score : grille de critères réglée par le recruteur
# --------------------------------------------------------------
def evaluer(cv, experience_min=2, experience_ideale=5, anglais_obligatoire=False,
            niveau_min="Aucun minimum", competences_demandees=()):
    """Score sur 100 et explication ligne par ligne :
       expérience 35, relation client 20, compétences demandées 25,
       anglais 10, niveau d'études 10."""
    annees = cv.get("annees_experience") or 0
    niveau = cv.get("niveau_bac_plus")
    langues = [p2.cle(l) for l in cv.get("langues") or []]
    connues = " | ".join(p2.cle(c) for c in (cv.get("competences") or [])
                         + (cv.get("competences_cles") or []))
    categories = {cv.get("categorie_poste")} | {p2.categorie_poste(x["Poste"])
                                                for x in cv.get("experiences") or []}
    relation_client = bool(categories & set(POSTES_RELATION_CLIENT))
    trouvees = [c for c in competences_demandees if p2.cle(c) in connues]
    anglais = "anglais" in langues

    points = {
        "Expérience": round(35 * min(annees / max(experience_ideale, 0.5), 1)),
        "Relation client": 20 if relation_client else 0,
        "Compétences demandées": round(25 * len(trouvees) / len(competences_demandees))
        if competences_demandees else 25,
        "Anglais": 10 if anglais else 0,
        NIVEAU: 10 if niveau is not None and niveau >= NIVEAUX[niveau_min] else 0,
    }
    detail = [
        f"Expérience : {annees:.1f} an(s)".replace(".", ",") + f" → {points['Expérience']}/35",
        f"Relation client : {'oui' if relation_client else 'non'} → {points['Relation client']}/20",
        f"Compétences demandées : {len(trouvees)}/{len(competences_demandees)}"
        f"{' (' + ', '.join(trouvees) + ')' if trouvees else ''} → {points['Compétences demandées']}/25"
        if competences_demandees else "Compétences demandées : aucune exigée → 25/25",
        f"Anglais : {'oui' if anglais else 'non'} → {points['Anglais']}/10",
        f"Niveau d'études : {cv.get('diplome') or 'non trouvé'} → {points[NIVEAU]}/10",
    ]
    manques = []
    if annees < experience_min:
        manques.append(f"moins de {experience_min} an(s) d'expérience")
    if anglais_obligatoire and not anglais:
        manques.append("pas d'anglais")
    if niveau_min != "Aucun minimum" and (niveau is None or niveau < NIVEAUX[niveau_min]):
        manques.append(f"niveau inférieur à {niveau_min}")
    return {"score": sum(points.values()), "detail": detail, "points": points,
            "statut": "Remplit les critères" if not manques else "Ne remplit pas : " + ", ".join(manques)}