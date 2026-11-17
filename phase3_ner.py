# ==============================================================
# PHASE 3 - Reconnaissance d'entités nommées (NER) avec spaCy
# Projet : Analyse de CV en apprentissage automatique avec Python, OCR et spaCy
#
# Trois parties, comme dans les instructions :
#   1. Découvrir la NER : le modèle français pré-entraîné de spaCy
#      appliqué aux CV nettoyés de la phase 2 (personnes, lieux, organisations)
#   2. Entraîner un modèle NER personnalisé sur des CV annotés
#      (fichier JSON : étiquette, début, fin, texte de chaque entité)
#   3. Évaluer le modèle : précision, rappel et score F, globalement
#      et par étiquette, puis l'appliquer aux CV de la phase 2
#
# Usage : python phase3_ner.py [fichier_json_annote]
#         (par défaut : donnees/cv_annotes.json, créé par generer_donnees_annotees.py)
# ==============================================================

import csv
import glob
import json
import os
import random
import re
import sys
import time

FICHIER_ANNOTE = sys.argv[1] if len(sys.argv) > 1 else os.path.join("donnees", "cv_annotes.json")
DOSSIER_TEXTES = os.path.join("resultats", "textes_nettoyes")      # sortie de la phase 2
DOSSIER_MODELE = "modele_ner"
DOSSIER_SORTIE = "resultats_ner"
EPOQUES = 15
TAILLE_LOT = 8
DROPOUT = 0.3
random.seed(42)


# ==============================================================
# 1. DÉCOUVERTE : la NER pré-entraînée de spaCy
# ==============================================================
def lire_cv_nettoyes():
    textes = {}
    for chemin in sorted(glob.glob(os.path.join(DOSSIER_TEXTES, "*.txt"))):
        with open(chemin, encoding="utf-8") as f:
            textes[os.path.basename(chemin)] = f.read()
    return textes


def decouverte_ner(spacy, textes):
    print("=" * 66)
    print("1. DÉCOUVERTE : modèle français pré-entraîné (fr_core_news_sm)")
    print("=" * 66)
    try:
        nlp = spacy.load("fr_core_news_sm")
    except OSError:
        print("Modèle absent -> python -m spacy download fr_core_news_sm\n")
        return
    print("Étiquettes connues :")
    for etiquette in nlp.get_pipe("ner").labels:
        print(f"  {etiquette:<5} {spacy.explain(etiquette)}")
    if not textes:
        print("\n(Aucun CV nettoyé trouvé : lancez d'abord les phases 1 et 2.)\n")
        return

    lignes = []
    for fichier, texte in textes.items():
        doc = nlp(texte)
        print(f"\n{fichier} : {len(doc.ents)} entités")
        for ent in doc.ents[:12]:
            print(f"  {ent.label_:<5} {ent.text!r}")
            lignes.append({"fichier": fichier, "etiquette": ent.label_, "texte": ent.text})
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "ner_preentraine.csv"), lignes)
    print("\nLimite : ce modèle connaît seulement les personnes, lieux, organisations")
    print("et « divers ». Il ne sait pas repérer un diplôme, une compétence ou un")
    print("poste : il faut entraîner un modèle personnalisé (partie 2).\n")


# ==============================================================
# 2a. PRÉPARATION DES DONNÉES ANNOTÉES
# ==============================================================
def charger_annotations(chemin):
    """Lit le JSON annoté (un CV par ligne) et corrige les défauts courants.
    Renvoie une liste de (texte, [(début, fin, étiquette)], partie) et un bilan."""
    bilan = {"cv": 0, "entites": 0, "fin_incluse_corrigee": 0, "espaces_retires": 0,
             "chevauchements_retires": 0, "incoherentes_retirees": 0}
    donnees = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.strip():
                continue
            cv = json.loads(ligne)
            texte = cv["content"]
            entites = []
            for annotation in cv.get("annotation") or []:
                etiquettes = annotation.get("label") or []
                if not etiquettes:
                    continue
                for point in annotation["points"]:
                    debut, fin, valeur = point["start"], point["end"], point.get("text", "")
                    # Dans ce format, la fin est souvent INCLUSE : spaCy veut une fin exclue
                    if texte[debut:fin + 1] == valeur:
                        fin += 1
                        bilan["fin_incluse_corrigee"] += 1
                    elif texte[debut:fin] != valeur:
                        bilan["incoherentes_retirees"] += 1
                        continue
                    # Espaces et ponctuation en bord d'entité : spaCy les refuse
                    d, f_ = debut, fin
                    while d < f_ and texte[d] in " \t\n.,;:":
                        d += 1
                    while f_ > d and texte[f_ - 1] in " \t\n.,;:":
                        f_ -= 1
                    if (d, f_) != (debut, fin):
                        bilan["espaces_retires"] += 1
                    if d < f_:
                        entites.append((d, f_, etiquettes[0]))
            entites, retires = retirer_chevauchements(entites)
            bilan["chevauchements_retires"] += retires
            bilan["cv"] += 1
            bilan["entites"] += len(entites)
            partie = (cv.get("extras") or {}).get("partie")
            donnees.append((texte, entites, partie))
    return donnees, bilan


def retirer_chevauchements(entites):
    """Un mot ne peut appartenir qu'à une seule entité : en cas de
    chevauchement, on garde la plus longue."""
    gardees, retires = [], 0
    for debut, fin, etiquette in sorted(entites, key=lambda e: (e[1] - e[0]), reverse=True):
        if any(debut < f and fin > d for d, f, _ in gardees):
            retires += 1
            continue
        gardees.append((debut, fin, etiquette))
    return sorted(gardees), retires


def separer(donnees):
    """Utilise la séparation indiquée dans le fichier, sinon 80 % / 20 % au hasard."""
    if all(partie in ("train", "test") for _, _, partie in donnees):
        train = [(t, e) for t, e, p in donnees if p == "train"]
        test = [(t, e) for t, e, p in donnees if p == "test"]
    else:
        melange = [(t, e) for t, e, _ in donnees]
        random.shuffle(melange)
        coupe = int(len(melange) * 0.8)
        train, test = melange[:coupe], melange[coupe:]
    return train, test


def vers_exemples(nlp, donnees, Example):
    """Transforme chaque CV en exemple spaCy. Une entité qui ne tombe pas
    sur des limites de mots (tokens) est ajustée, ou retirée si impossible."""
    exemples, ajustees, retirees = [], 0, 0
    for texte, entites in donnees:
        doc = nlp.make_doc(texte)
        propres = []
        for debut, fin, etiquette in entites:
            span = doc.char_span(debut, fin, label=etiquette)
            if span is None:
                span = doc.char_span(debut, fin, label=etiquette, alignment_mode="contract")
                if span is None or len(span) == 0:
                    retirees += 1
                    continue
                ajustees += 1
            propres.append((span.start_char, span.end_char, etiquette))
        exemples.append(Example.from_dict(doc, {"entities": propres}))
    return exemples, ajustees, retirees


# ==============================================================
# 2b. ENTRAÎNEMENT DU MODÈLE PERSONNALISÉ
# ==============================================================
def entrainer(spacy, train, test, etiquettes):
    from spacy.util import minibatch

    nlp = spacy.blank("fr")                    # tokeniseur français, aucune connaissance NER
    ner = nlp.add_pipe("ner")
    for etiquette in etiquettes:
        ner.add_label(etiquette)
    optimiseur = nlp.initialize(get_examples=lambda: train)

    historique = []
    print(f"\n{'Époque':>6} {'Perte':>10} {'Précision':>10} {'Rappel':>8} {'Score F':>8}")
    for epoque in range(1, EPOQUES + 1):
        random.shuffle(train)
        pertes = {}
        for lot in minibatch(train, size=TAILLE_LOT):
            # Passage avant, calcul de la perte, rétropropagation et mise à jour
            nlp.update(lot, drop=DROPOUT, sgd=optimiseur, losses=pertes)
        scores = nlp.evaluate(test)
        historique.append({"epoque": epoque, "perte": pertes["ner"],
                           "precision": scores["ents_p"], "rappel": scores["ents_r"],
                           "f": scores["ents_f"]})
        print(f"{epoque:>6} {pertes['ner']:>10.1f} {scores['ents_p']:>10.2%} "
              f"{scores['ents_r']:>8.2%} {scores['ents_f']:>8.2%}")
    return nlp, historique


# ==============================================================
# 2c. RÈGLES + MODÈLE : un système hybride
# ==============================================================
# Un e-mail ou un numéro de téléphone a une forme très régulière : une
# expression régulière le reconnaît à coup sûr, quelle que soit la mise en
# page. Les règles passent AVANT le modèle, qui respecte les entités déjà
# trouvées et se concentre sur celles qui demandent le contexte.
MOTIF_EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
MOTIF_TELEPHONE = r"(?:\(?(?:\+|00)\d{3}\)?\s?)?\b(?:7[05678]|33)\s?\d{3}\s?\d{2}\s?\d{2}\b"
# Étiquettes qui peuvent ne contenir aucune lettre
SANS_LETTRES_AUTORISEES = {"DATE", "TELEPHONE"}


def ajouter_regles(nlp):
    from spacy.language import Language
    from spacy.util import filter_spans

    if not Language.has_factory("regles_coordonnees"):
        @Language.component("regles_coordonnees")
        def regles_coordonnees(doc):
            trouves = []
            for motif, etiquette in ((MOTIF_EMAIL, "EMAIL"), (MOTIF_TELEPHONE, "TELEPHONE")):
                for m in re.finditer(motif, doc.text):
                    span = doc.char_span(m.start(), m.end(), label=etiquette,
                                         alignment_mode="expand")
                    if span is not None:
                        trouves.append(span)
            doc.ents = filter_spans(list(doc.ents) + trouves)
            return doc

        @Language.component("filtre_entites")
        def filtre_entites(doc):
            # Retire les entités absurdes : « 112 » étiqueté POSTE, ou un
            # « téléphone » qui n'a pas la forme d'un numéro de téléphone
            gardees = []
            for e in doc.ents:
                if e.label_ == "TELEPHONE" and not re.fullmatch(MOTIF_TELEPHONE, e.text.strip()):
                    continue
                if e.label_ == "EMAIL" and not re.fullmatch(MOTIF_EMAIL, e.text.strip()):
                    continue
                if e.label_ not in SANS_LETTRES_AUTORISEES \
                        and len(re.findall(r"[A-Za-zÀ-ÿ]", e.text)) < 2:
                    continue
                gardees.append(e)
            doc.ents = gardees
            return doc

    nlp.add_pipe("regles_coordonnees", before="ner")
    nlp.add_pipe("filtre_entites", after="ner")
    return nlp


def comparer(scores_modele, scores_hybride):
    print("\n=== Modèle seul ou modèle + règles (CV de test) ===")
    print(f"{'':<16}{'Modèle seul':>14}{'Modèle + règles':>18}")
    print(f"{'Score F global':<16}{scores_modele['ents_f']:>14.2%}{scores_hybride['ents_f']:>18.2%}")
    for etiquette in ("EMAIL", "TELEPHONE"):
        avant = scores_modele["ents_per_type"].get(etiquette, {}).get("f", 0)
        apres = scores_hybride["ents_per_type"].get(etiquette, {}).get("f", 0)
        print(f"{etiquette:<16}{avant:>14.2%}{apres:>18.2%}")


# ==============================================================
# 3. ÉVALUATION
# ==============================================================
def evaluer(nlp, test):
    scores = nlp.evaluate(test)
    print("\n" + "=" * 66)
    print("3. ÉVALUATION sur les CV de test (jamais vus pendant l'entraînement)")
    print("=" * 66)
    print(f"Précision : {scores['ents_p']:.2%}  (parmi les entités trouvées, part de justes)")
    print(f"Rappel    : {scores['ents_r']:.2%}  (parmi les vraies entités, part trouvée)")
    print(f"Score F   : {scores['ents_f']:.2%}  (moyenne harmonique des deux)")

    par_type = scores["ents_per_type"]
    print(f"\n{'Étiquette':<14} {'Précision':>10} {'Rappel':>8} {'Score F':>8}")
    lignes = []
    for etiquette, s in sorted(par_type.items(), key=lambda x: -x[1]["f"]):
        print(f"{etiquette:<14} {s['p']:>10.2%} {s['r']:>8.2%} {s['f']:>8.2%}")
        lignes.append({"etiquette": etiquette, "precision": round(s["p"], 4),
                       "rappel": round(s["r"], 4), "score_f": round(s["f"], 4)})
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "scores_par_etiquette.csv"), lignes)
    return scores, lignes


def analyser_erreurs(nlp, test, maximum=12):
    """Compare les entités prédites aux vraies entités pour comprendre les erreurs."""
    erreurs = []
    for exemple in test:
        vraies = {(e.start_char, e.end_char, e.label_) for e in exemple.reference.ents}
        doc = nlp(exemple.reference.text)
        predites = {(e.start_char, e.end_char, e.label_) for e in doc.ents}
        texte = exemple.reference.text
        for d, f, l in vraies - predites:
            erreurs.append({"type": "manquée ou mal délimitée", "etiquette": l, "texte": texte[d:f]})
        for d, f, l in predites - vraies:
            erreurs.append({"type": "en trop ou mal étiquetée", "etiquette": l, "texte": texte[d:f]})
    print(f"\n=== Analyse des erreurs : {len(erreurs)} au total (exemples) ===")
    for e in erreurs[:maximum]:
        print(f"  {e['type']:<26} {e['etiquette']:<14} {e['texte'][:40]!r}")
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "erreurs.csv"), erreurs)


def appliquer_aux_cv(nlp, textes):
    if not textes:
        return
    print("\n=== Application du modèle aux CV nettoyés de la phase 2 ===")
    resultats = {}
    for fichier, texte in textes.items():
        doc = nlp(texte)
        entites = {}
        for ent in doc.ents:
            entites.setdefault(ent.label_, []).append(ent.text)
        resultats[fichier] = entites
        print(f"\n{fichier}")
        for etiquette, valeurs in sorted(entites.items()):
            print(f"  {etiquette:<14} {' | '.join(valeurs)[:90]}")
    with open(os.path.join(DOSSIER_SORTIE, "entites_cv.json"), "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)


def graphiques(historique, lignes):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    ep = [h["epoque"] for h in historique]
    ax1.plot(ep, [h["perte"] for h in historique], "o-")
    ax1.set_title("Perte d'entraînement")
    ax1.set_xlabel("Époque")
    ax1b = ax1.twinx()
    ax1b.plot(ep, [h["f"] for h in historique], "s--", color="tab:green")
    ax1b.set_ylabel("Score F (test)", color="tab:green")
    lignes = sorted(lignes, key=lambda l: l["score_f"])
    ax2.barh([l["etiquette"] for l in lignes], [l["score_f"] for l in lignes], color="tab:blue")
    ax2.set_xlim(0, 1)
    ax2.set_title("Score F par étiquette (test)")
    for i, l in enumerate(lignes):
        ax2.text(l["score_f"] + 0.01, i, f"{l['score_f']:.2f}", va="center", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(DOSSIER_SORTIE, "ner_courbes.png"), dpi=120)


def ecrire_csv(chemin, lignes):
    if not lignes:
        return
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=lignes[0].keys(), delimiter=";")
        ecrivain.writeheader()
        ecrivain.writerows(lignes)


# ==============================================================
# PROGRAMME PRINCIPAL
# ==============================================================
def main():
    import spacy
    from spacy.training import Example

    os.makedirs(DOSSIER_SORTIE, exist_ok=True)
    textes = lire_cv_nettoyes()

    # 1. Découverte
    decouverte_ner(spacy, textes)

    # 2. Données annotées
    print("=" * 66)
    print("2. ENTRAÎNEMENT d'un modèle NER personnalisé")
    print("=" * 66)
    if not os.path.exists(FICHIER_ANNOTE):
        print(f"Fichier {FICHIER_ANNOTE} introuvable.")
        print("-> python generer_donnees_annotees.py, ou indiquez votre fichier JSON.")
        return
    donnees, bilan = charger_annotations(FICHIER_ANNOTE)
    print(f"Fichier : {FICHIER_ANNOTE}")
    print(f"  {bilan['cv']} CV, {bilan['entites']} entités après corrections")
    print(f"  fins incluses converties : {bilan['fin_incluse_corrigee']}, "
          f"espaces retirés : {bilan['espaces_retires']}, "
          f"chevauchements retirés : {bilan['chevauchements_retires']}, "
          f"annotations incohérentes : {bilan['incoherentes_retirees']}")

    train_brut, test_brut = separer(donnees)
    nlp_tmp = spacy.blank("fr")
    train, aj1, re1 = vers_exemples(nlp_tmp, train_brut, Example)
    test, aj2, re2 = vers_exemples(nlp_tmp, test_brut, Example)
    print(f"  {len(train)} CV d'entraînement, {len(test)} CV de test")
    print(f"  alignement sur les mots : {aj1 + aj2} entités ajustées, {re1 + re2} retirées")
    etiquettes = sorted({e[2] for _, ents, _ in donnees for e in ents})
    print(f"  étiquettes : {', '.join(etiquettes)}")

    debut = time.time()
    nlp, historique = entrainer(spacy, train, test, etiquettes)
    print(f"Durée de l'entraînement : {(time.time() - debut) / 60:.1f} min")
    nlp.to_disk(DOSSIER_MODELE)
    print(f"Modèle enregistré dans le dossier « {DOSSIER_MODELE} » (sans les règles,")
    print("qui sont ajoutées par la fonction ajouter_regles au moment de l'utiliser)")
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "historique_entrainement.csv"), historique)

    # Règles + modèle
    scores_modele = nlp.evaluate(test)
    ajouter_regles(nlp)
    scores_hybride = nlp.evaluate(test)
    comparer(scores_modele, scores_hybride)

    # 3. Évaluation (système final : modèle + règles)
    _, lignes = evaluer(nlp, test)
    analyser_erreurs(nlp, test)
    graphiques(historique, lignes)
    appliquer_aux_cv(nlp, textes)
    print(f"\nRésultats enregistrés dans le dossier « {DOSSIER_SORTIE} »")


if __name__ == "__main__":
    main()
