# ==============================================================
# Tests automatiques du projet, à lancer APRÈS chaque phase et
# AVANT chaque envoi sur GitHub.
#
# Les CV fictifs de cv_exemples/ ont un contenu connu : on vérifie que
# chaque phase retrouve les bonnes informations.
#
# Usage : python tester_projet.py          (toutes les phases déjà lancées)
#         python tester_projet.py 2        (une seule phase)
# ==============================================================

import csv
import json
import os
import re
import sys

reussis, echecs = 0, 0


def verifier(description, condition, detail=""):
    global reussis, echecs
    if condition:
        reussis += 1
        print(f"  [OK]     {description}")
    else:
        echecs += 1
        print(f"  [ÉCHEC]  {description}" + (f"  ->  {detail}" if detail else ""))


def charger_json(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def par_nom(liste):
    return {cv["nom"]: cv for cv in liste if cv.get("nom")}


# --------------------------------------------------------------
def tester_phase1():
    print("\n=== Phase 1 : extraction ===")
    chemin = os.path.join("resultats", "cv_extraits.json")
    if not os.path.exists(chemin):
        verifier("résultats de la phase 1 présents", False, "lancez phase1_extraction.py")
        return
    cvs = par_nom(charger_json(chemin))
    attendus = {
        "Aminata Ndiaye": ("texte PDF", "aminata.ndiaye@example.com"),
        "Awa Sarr": ("OCR (PDF scanné)", "awa.sarr@example.com"),
        "Ibrahima Ba": ("texte Word", "ibrahima.ba@example.com"),
        "Moussa Fall": ("OCR (image)", "moussa.fall@example.com"),
    }
    verifier("4 CV analysés, un par format", len(cvs) == 4, f"{len(cvs)} trouvés : {list(cvs)}")
    for nom, (methode, email) in attendus.items():
        cv = cvs.get(nom)
        verifier(f"{nom} : nom trouvé", cv is not None)
        if not cv:
            continue
        verifier(f"{nom} : méthode « {methode} »", cv["methode_extraction"] == methode,
                 cv["methode_extraction"])
        if methode.startswith("OCR"):
            # L'OCR peut déformer un caractère : la phase 2 vérifie la valeur exacte
            verifier(f"{nom} : e-mail trouvé", "@" in (cv["email"] or ""), cv["email"])
        else:
            verifier(f"{nom} : e-mail correct", cv["email"] == email, cv["email"])
        verifier(f"{nom} : téléphone trouvé", bool(cv["telephone"]))
        verifier(f"{nom} : au moins 3 compétences", len(cv["competences"]) >= 3,
                 cv["competences"])
        verifier(f"{nom} : au moins 2 langues", len(cv["langues"]) >= 2, cv["langues"])
    if "Awa Sarr" in cvs:
        confiance = cvs["Awa Sarr"]["confiance_ocr"] or 0
        verifier("confiance OCR du scan supérieure à 60/100", confiance > 60, confiance)


# --------------------------------------------------------------
def tester_phase2():
    print("\n=== Phase 2 : nettoyage ===")
    chemin = os.path.join("resultats", "cv_nettoyes.json")
    if not os.path.exists(chemin):
        verifier("résultats de la phase 2 présents", False, "lancez phase2_nettoyage.py")
        return
    cvs = par_nom(charger_json(chemin))
    emails = {"Aminata Ndiaye": "aminata.ndiaye@example.com", "Awa Sarr": "awa.sarr@example.com",
              "Ibrahima Ba": "ibrahima.ba@example.com", "Moussa Fall": "moussa.fall@example.com"}
    for nom, email in emails.items():
        if nom in cvs:
            verifier(f"{nom} : e-mail exact après nettoyage", cvs[nom]["email"] == email,
                     cvs[nom]["email"])
    for nom, cv in cvs.items():
        verifier(f"{nom} : téléphone au format +221 XX XXX XX XX",
                 bool(re.fullmatch(r"\+221 \d{2} \d{3} \d{2} \d{2}", cv["telephone"] or "")),
                 cv["telephone"])
        verifier(f"{nom} : catégorie de poste connue", cv["categorie_poste"] not in (None, "Autre"),
                 cv["categorie_poste"])
        verifier(f"{nom} : niveau d'études renseigné", cv["niveau_bac_plus"] is not None)
    if "Ibrahima Ba" in cvs:
        annees = cvs["Ibrahima Ba"]["annees_experience"] or 0
        verifier("Ibrahima Ba : date « 03/2019 » prise en compte (plus de 7 ans)", annees >= 7, annees)
    if "Awa Sarr" in cvs:
        verifier("Awa Sarr : année commune comptée une seule fois (4,0 ans)",
                 cvs["Awa Sarr"]["annees_experience"] == 4.0, cvs["Awa Sarr"]["annees_experience"])
    chemin_texte = os.path.join("resultats", "textes_nettoyes", "cv_ibrahima_ba.txt")
    if os.path.exists(chemin_texte):
        texte = open(chemin_texte, encoding="utf-8").read()
        verifier("informations personnelles retirées (date de naissance, nationalité)",
                 "Né le" not in texte and "Nationalité" not in texte)
        verifier("section centres d'intérêt retirée", "Football" not in texte)
        verifier("numéro de page retiré", "Page 1/1" not in texte)
    chemin_texte = os.path.join("resultats", "textes_nettoyes", "cv_aminata_ndiaye.txt")
    if os.path.exists(chemin_texte):
        texte = open(chemin_texte, encoding="utf-8").read()
        verifier("séparateur gardé entre le téléphone et l'e-mail",
                 re.search(r"\d{2} - aminata", texte) is not None,
                 texte.splitlines()[2] if len(texte.splitlines()) > 2 else "")
    verifier("journal des corrections présent",
             os.path.exists(os.path.join("resultats", "journal_nettoyage.csv")))


# --------------------------------------------------------------
def tester_phase3():
    print("\n=== Phase 3 : reconnaissance d'entités ===")
    dossier = "resultats_ner"
    chemin_scores = os.path.join(dossier, "scores_par_etiquette.csv")
    if not os.path.exists(chemin_scores):
        verifier("résultats de la phase 3 présents", False, "lancez phase3_ner.py")
        return
    verifier("modèle enregistré", os.path.isdir("modele_ner"))
    with open(os.path.join(dossier, "historique_entrainement.csv"), encoding="utf-8-sig") as f:
        historique = list(csv.DictReader(f, delimiter=";"))
    pertes = [float(h["perte"]) for h in historique]
    verifier("la perte diminue pendant l'entraînement", pertes[-1] < pertes[0],
             f"{pertes[0]:.1f} -> {pertes[-1]:.1f}")
    f_final = float(historique[-1]["f"])
    verifier("score F global d'au moins 80 % sur le test", f_final >= 0.80, f"{f_final:.2%}")
    with open(chemin_scores, encoding="utf-8-sig") as f:
        scores = list(csv.DictReader(f, delimiter=";"))
    verifier("11 étiquettes évaluées", len(scores) == 11, len(scores))
    for ligne in scores:
        score = float(ligne["score_f"])
        verifier(f"{ligne['etiquette']} : score F d'au moins 50 %", score >= 0.5, f"{score:.2%}")
    chemin_cv = os.path.join(dossier, "entites_cv.json")
    if os.path.exists(chemin_cv):
        entites = charger_json(chemin_cv)
        trouve = entites.get("cv_aminata_ndiaye.txt", {})
        verifier("CV d'Aminata Ndiaye : e-mail reconnu comme EMAIL",
                 any("aminata.ndiaye@example.com" in e for e in trouve.get("EMAIL", [])),
                 trouve.get("EMAIL"))
        telephones = [t for cv in entites.values() for t in cv.get("TELEPHONE", [])]
        verifier("aucun téléphone ne contient d'e-mail ou de lettres",
                 all(not re.search(r"[A-Za-z@]", t) for t in telephones), telephones)
        postes = [p for cv in entites.values() for p in cv.get("POSTE", [])]
        verifier("aucun poste sans lettres (ex. « 112 »)",
                 all(re.search(r"[A-Za-zÀ-ÿ]{2}", p) for p in postes), postes)


# --------------------------------------------------------------
def tester_phase4():
    print("\n=== Phase 4 : extraction des relations ===")
    dossier = "resultats_relations"
    chemin = os.path.join(dossier, "scores_techniques.csv")
    if not os.path.exists(chemin):
        verifier("résultats de la phase 4 présents", False, "lancez phase4_relations.py")
        return
    with open(chemin, encoding="utf-8-sig") as f:
        scores = {l["technique"]: float(l["score_f"]) for l in csv.DictReader(f, delimiter=";")}
    verifier("5 techniques évaluées", len(scores) == 5, list(scores))
    meilleure = max(scores.values())
    verifier("meilleure technique : score F d'au moins 80 %", meilleure >= 0.80, f"{meilleure:.2%}")
    verifier("la meilleure technique bat la co-occurrence",
             meilleure > scores.get("Co-occurrence", 1), scores)
    verifier("la règle de mise en page améliore les dépendances",
             scores.get("Dépendances + mise en page", 0) >= scores.get("Dépendances", 1), scores)
    verifier("arbre de dépendances dessiné",
             os.path.exists(os.path.join(dossier, "arbre_dependances.html")))
    chemin_fiches = os.path.join(dossier, "fiches_cv.json")
    if os.path.exists(chemin_fiches):
        fiches = charger_json(chemin_fiches)
        aminata = fiches.get("cv_aminata_ndiaye.txt", {})
        employeurs = [e for x in aminata.get("experiences", []) for e in x["entreprise"]]
        verifier("Aminata Ndiaye : un poste relié à TéléServices Afrique",
                 any("TéléServices" in e for e in employeurs), employeurs)


def tester_phase5():
    print("\n=== Phase 5 : base de données et modélisation ===")
    import sqlite3
    dossier = "resultats_bdd"
    base = os.path.join(dossier, "base_cv.db")
    if not os.path.exists(base):
        verifier("base de données présente", False, "lancez phase5_base_donnees.py")
        return
    con = sqlite3.connect(base)
    valeur = lambda sql: con.execute(sql).fetchone()[0]
    tables = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    attendues = {"candidats", "experiences", "formations", "competences", "candidat_competences",
                 "rejets", "decisions", "predictions"}
    verifier("les 8 tables du schéma existent", attendues <= tables, sorted(tables))
    verifier("400 CV fictifs intégrés", valeur("SELECT COUNT(*) FROM candidats WHERE source = 'fictif'") == 400)
    verifier("4 CV d'exemple intégrés", valeur("SELECT COUNT(*) FROM candidats WHERE source = 'exemple'") == 4)
    verifier("aucune clé étrangère cassée", not con.execute("PRAGMA foreign_key_check").fetchall())
    verifier("chaque compétence n'est enregistrée qu'une fois",
             valeur("SELECT COUNT(*) FROM (SELECT cle, type FROM competences "
                    "GROUP BY cle, type HAVING COUNT(*) > 1)") == 0)
    verifier("la plupart des expériences fictives ont des dates",
             valeur("SELECT AVG(date_debut IS NOT NULL) FROM experiences e JOIN candidats c "
                    "ON c.id = e.candidat_id WHERE c.source = 'fictif'") >= 0.95)
    verifier("Aminata Ndiaye : TéléServices Afrique depuis mars 2022",
             valeur("SELECT COUNT(*) FROM experiences e JOIN candidats c ON c.id = e.candidat_id "
                    "WHERE c.nom = 'Aminata Ndiaye' AND e.entreprise LIKE 'TéléServices%' "
                    "AND e.date_debut = '2022-03'") == 1)
    verifier("Moussa Fall : Master 1 enregistré (Bac+4)",
             valeur("SELECT COUNT(*) FROM formations f JOIN candidats c ON c.id = f.candidat_id "
                    "WHERE c.nom = 'Moussa Fall' AND f.niveau = 4") == 1)
    verifier("informations douteuses écartées dans « rejets »",
             valeur("SELECT COUNT(*) FROM rejets") >= 1)
    verifier("décisions passées pour les 400 CV fictifs", valeur("SELECT COUNT(*) FROM decisions") == 400)
    verifier("requêtes SQL enregistrées", os.path.exists(os.path.join(dossier, "requetes.sql")))
    chemin = os.path.join(dossier, "scores_modeles.csv")
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8-sig") as f:
            scores = {l["modele"]: float(l["auc_validation_croisee"])
                      for l in csv.DictReader(f, delimiter=";")}
        verifier("3 modèles comparés", len(scores) == 3, list(scores))
        verifier("meilleur modèle : AUC d'au moins 0,75", max(scores.values()) >= 0.75, scores)
    else:
        verifier("scores des modèles présents", False)
    probas = [p for (p,) in con.execute("SELECT probabilite FROM predictions")]
    verifier("les 4 nouvelles candidatures sont classées",
             len(probas) == 4 and all(0 <= p <= 1 for p in probas), probas)
    con.close()


# --------------------------------------------------------------
def main():
    phases = sys.argv[1:] or ["1", "2", "3", "4", "5"]
    tests = {"1": tester_phase1, "2": tester_phase2, "3": tester_phase3, "4": tester_phase4, "5": tester_phase5}
    for phase in phases:
        tests[phase]()
    print(f"\n=== {reussis} tests réussis, {echecs} échecs ===")
    if echecs:
        print("Corrigez les échecs avant d'envoyer sur GitHub.")
    else:
        print("Tout est bon : vous pouvez envoyer sur GitHub.")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
