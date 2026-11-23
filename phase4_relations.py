# ==============================================================
# PHASE 4 - Extraction des relations entre entités
# Projet : Analyse de CV en apprentissage automatique avec Python, OCR et spaCy
#
# Une fois les entités trouvées (phase 3), on relie celles qui vont ensemble :
#   A_OCCUPE   NOM -> POSTE            la personne a occupé ce poste
#   EMPLOYEUR  POSTE -> ENTREPRISE     où le poste a été occupé
#   PERIODE    POSTE -> DATE           quand
#   LIEU       ENTREPRISE -> VILLE
#   ECOLE      DIPLOME -> ETABLISSEMENT
#   OBTENU_EN  DIPLOME -> DATE
#
# Trois parties, comme dans les instructions :
#   1. Plusieurs techniques d'extraction, de la plus simple à la plus fine :
#      co-occurrence, proximité, analyse des dépendances syntaxiques, et
#      ajout d'une règle de mise en page (dates écrites sous le poste)
#   2. Analyse des dépendances avec spaCy : exemple commenté et arbre dessiné
#   3. Validation par rapport à la vérité terrain (CV annotés à la main) :
#      précision, rappel et score F de chaque technique, puis du système
#      complet (entités prédites par le modèle de la phase 3)
#
# Usage : python phase4_relations.py
#   (données : donnees/cv_relations.json, créé par generer_donnees_relations.py)
# ==============================================================

import csv
import glob
import json
import os
import re
import unicodedata

FICHIER_RELATIONS = os.path.join("donnees", "cv_relations.json")
DOSSIER_TEXTES = os.path.join("resultats", "textes_nettoyes")     # sortie de la phase 2
DOSSIER_MODELE_NER = "modele_ner"                                   # sortie de la phase 3
DOSSIER_SORTIE = "resultats_relations"
DISTANCE_MAX = 8        # nombre maximal d'arcs entre deux entités dans l'arbre syntaxique

# (étiquette de la tête, étiquette de la queue) -> type de relation
TYPES = {
    ("NOM", "POSTE"): "A_OCCUPE",
    ("POSTE", "ENTREPRISE"): "EMPLOYEUR",
    ("POSTE", "DATE"): "PERIODE",
    ("ENTREPRISE", "VILLE"): "LIEU",
    ("DIPLOME", "ETABLISSEMENT"): "ECOLE",
    ("DIPLOME", "DATE"): "OBTENU_EN",
}
# Pour chaque étiquette de queue, les têtes possibles (sauf NOM, traité à part)
TETES_POSSIBLES = {}
for (tete, queue) in TYPES:
    if tete != "NOM":
        TETES_POSSIBLES.setdefault(queue, []).append(tete)

TITRES_SECTIONS = {
    "experiences professionnelles", "experience professionnelle", "parcours professionnel",
    "experiences", "experience", "formation", "formations", "parcours scolaire", "education",
    "diplomes", "competences", "competences cles", "savoir faire", "langues",
    "langues parlees", "profil", "certifications",
}


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", " ", texte).strip()


# ==============================================================
# PRÉPARATION : entités rangées par ligne
# ==============================================================
def preparer(texte, entites):
    """entites : liste de dict {start, end, label, text}. Ajoute à chacune son
    numéro de ligne et indique si elle est dans l'en-tête du CV (avant le
    premier titre de section : nom, poste visé, coordonnées)."""
    lignes, position = [], 0
    for ligne in texte.split("\n"):
        lignes.append((position, position + len(ligne)))
        position += len(ligne) + 1
    fin_en_tete = next((i for i, (d, f) in enumerate(lignes)
                        if normaliser(texte[d:f]) in TITRES_SECTIONS), len(lignes))
    for e in entites:
        e["ligne"] = next(i for i, (d, f) in enumerate(lignes) if d <= e["start"] <= f)
        e["en_tete"] = e["ligne"] < fin_en_tete
    return lignes


def cle(e):
    return (e["start"], e["end"])


def relation(tete, queue):
    return (TYPES[(tete["label"], queue["label"])], cle(tete), cle(queue))


def regle_document(entites):
    """Un CV décrit UNE personne : son nom est relié à tous les postes qu'elle
    a occupés (ceux du corps du CV, pas le poste visé de l'en-tête)."""
    noms = [e for e in entites if e["label"] == "NOM" and e["en_tete"]]
    if not noms:
        return set()
    return {relation(noms[0], e) for e in entites if e["label"] == "POSTE" and not e["en_tete"]}


def par_ligne(entites):
    lignes = {}
    for e in entites:
        if not e["en_tete"]:
            lignes.setdefault(e["ligne"], []).append(e)
    return lignes


# ==============================================================
# 1. TECHNIQUES D'EXTRACTION
# ==============================================================
def cooccurrence(texte, entites, nlp=None):
    """Technique 1 : deux entités compatibles sur la même ligne sont reliées."""
    relations = regle_document(entites)
    for groupe in par_ligne(entites).values():
        for tete in groupe:
            for queue in groupe:
                if (tete["label"], queue["label"]) in TYPES and tete["label"] != "NOM":
                    relations.add(relation(tete, queue))
    return relations


def proximite(texte, entites, nlp=None):
    """Technique 2 : chaque entité est reliée à la tête compatible la plus
    proche sur la même ligne (en nombre de caractères)."""
    relations = regle_document(entites)
    for groupe in par_ligne(entites).values():
        for queue in groupe:
            candidates = [t for t in groupe if t["label"] in TETES_POSSIBLES.get(queue["label"], [])]
            if candidates:
                tete = min(candidates, key=lambda t: max(t["start"] - queue["end"],
                                                         queue["start"] - t["end"], 0))
                relations.add(relation(tete, queue))
    return relations


def chemin_syntaxique(a, b):
    """Nombre d'arcs entre deux mots dans l'arbre de dépendances : on remonte
    de chaque mot vers la racine jusqu'à leur premier ancêtre commun."""
    ancetres_a = [a] + list(a.ancestors)
    positions_a = {t.i: n for n, t in enumerate(ancetres_a)}
    for n, t in enumerate([b] + list(b.ancestors)):
        if t.i in positions_a:
            return positions_a[t.i] + n
    return None                          # pas dans la même phrase


def dependances(texte, entites, nlp):
    """Technique 3 : chaque ligne est analysée par le parseur de spaCy ; une
    entité est reliée à la tête compatible la plus proche DANS L'ARBRE
    syntaxique (et non dans le texte)."""
    relations = regle_document(entites)
    groupes = par_ligne(entites)
    lignes = texte.split("\n")
    debuts = [0]
    for ligne in lignes[:-1]:
        debuts.append(debuts[-1] + len(ligne) + 1)
    numeros = sorted(groupes)
    for numero, doc in zip(numeros, nlp.pipe(lignes[n] for n in numeros)):
        groupe = groupes[numero]
        racines = {}
        for e in groupe:
            span = doc.char_span(e["start"] - debuts[numero], e["end"] - debuts[numero],
                                 alignment_mode="expand")
            if span is not None and len(span):
                racines[cle(e)] = span.root          # mot principal de l'entité
        for queue in groupe:
            if cle(queue) not in racines:
                continue
            meilleure, distance_min = None, None
            for tete in groupe:
                if tete["label"] not in TETES_POSSIBLES.get(queue["label"], []) \
                        or cle(tete) not in racines:
                    continue
                d = chemin_syntaxique(racines[cle(tete)], racines[cle(queue)])
                if d is None or d > DISTANCE_MAX:
                    continue
                # À égalité dans l'arbre : en français, une précision (entreprise,
                # dates) suit le poste qu'elle décrit -> tête placée AVANT, la plus proche
                apres = 0 if tete["start"] < queue["start"] else 1
                rang = (d, apres, abs(tete["start"] - queue["start"]))
                if meilleure is None or rang < distance_min:
                    meilleure, distance_min = tete, rang
            if meilleure:
                relations.add(relation(meilleure, queue))
    return relations


def mise_en_page(entites, relations):
    """Règle de mise en page : une date seule sur sa ligne (« Mars 2022 -
    Décembre 2024 ») appartient au poste ou au diplôme de la ligne au-dessus."""
    relations = set(relations)
    groupes = par_ligne(entites)
    for numero, groupe in groupes.items():
        if any(e["label"] in ("POSTE", "DIPLOME") for e in groupe):
            continue
        for decalage in (1, 2):
            precedente = [e for e in groupes.get(numero - decalage, [])
                          if e["label"] in ("POSTE", "DIPLOME")]
            if precedente:
                tete = precedente[-1]
                for queue in groupe:
                    if queue["label"] == "DATE":
                        relations.add(relation(tete, queue))
                break
    return relations


METHODES = {
    "Co-occurrence": lambda t, e, nlp: cooccurrence(t, e),
    "Proximité": lambda t, e, nlp: proximite(t, e),
    "Proximité + mise en page": lambda t, e, nlp: mise_en_page(e, proximite(t, e)),
    "Dépendances": dependances,
    "Dépendances + mise en page": lambda t, e, nlp: mise_en_page(e, dependances(t, e, nlp)),
}


# ==============================================================
# 2. ANALYSE DES DÉPENDANCES : EXEMPLE COMMENTÉ
# ==============================================================
def demonstration(nlp, spacy):
    phrase = ("J'ai travaillé comme conseillère clientèle chez Kora Contact à Thiès de 2019 "
              "à 2021, puis comme téléconseillère chez Ndar Télécom de 2022 à 2024.")
    entites_demo = [("conseillère clientèle", "POSTE"), ("Kora Contact", "ENTREPRISE"),
                    ("Thiès", "VILLE"), ("2019", "DATE"), ("2021", "DATE"),
                    ("téléconseillère", "POSTE"), ("Ndar Télécom", "ENTREPRISE"),
                    ("2022", "DATE"), ("2024", "DATE")]
    entites = []
    for valeur, etiquette in entites_demo:
        debut = phrase.index(valeur)
        entites.append({"start": debut, "end": debut + len(valeur), "label": etiquette,
                        "text": valeur})
    texte = "EXPÉRIENCES\n" + phrase
    for e in entites:
        e["start"] += 12
        e["end"] += 12
    preparer(texte, entites)

    print("=" * 66)
    print("2. ANALYSE DES DÉPENDANCES : exemple")
    print("=" * 66)
    print(f"« {phrase} »\n")
    doc = nlp(phrase)
    print(f"  {'Mot':<16}{'Relation':<12}{'Rattaché à'}")
    for token in doc:
        if not token.is_punct:
            print(f"  {token.text:<16}{token.dep_:<12}{token.head.text}")
    print("\nLecture : chaque mot est rattaché à un autre (sa « tête ») par une relation")
    print("grammaticale (nsubj = sujet, obl = complément, nmod = complément du nom…).")

    # Vérité terrain de la phrase : 7 relations
    par_texte = {e["text"]: cle(e) for e in entites}
    attendues = {("EMPLOYEUR", "conseillère clientèle", "Kora Contact"), ("LIEU", "Kora Contact", "Thiès"),
                 ("PERIODE", "conseillère clientèle", "2019"), ("PERIODE", "conseillère clientèle", "2021"),
                 ("EMPLOYEUR", "téléconseillère", "Ndar Télécom"),
                 ("PERIODE", "téléconseillère", "2022"), ("PERIODE", "téléconseillère", "2024")}
    attendues = {(t, par_texte[a], par_texte[b]) for t, a, b in attendues}
    textes_trouves = {cle(e): e["text"] for e in entites}
    for nom_methode in ("Co-occurrence", "Proximité", "Dépendances"):
        trouvees = METHODES[nom_methode](texte, entites, nlp)
        justes = len(trouvees & attendues)
        print(f"\n« {nom_methode} » : {len(trouvees)} relations trouvées, {justes} justes sur 7")
        for type_rel, tete, queue in sorted(trouvees, key=lambda r: (r[1], r[0], r[2])):
            marque = "  " if (type_rel, tete, queue) in attendues else "x "
            print(f"  {marque}{textes_trouves[tete]:<22} --{type_rel}--> {textes_trouves[queue]}")
    print("(x = relation fausse)")

    html = spacy.displacy.render(doc, style="dep", page=True,
                                 options={"compact": True, "distance": 110})
    with open(os.path.join(DOSSIER_SORTIE, "arbre_dependances.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nArbre dessiné : {DOSSIER_SORTIE}/arbre_dependances.html (à ouvrir dans le navigateur)\n")


# ==============================================================
# 3. VALIDATION PAR RAPPORT À LA VÉRITÉ TERRAIN
# ==============================================================
def charger_verite_terrain(chemin):
    cvs = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.strip():
                continue
            cv = json.loads(ligne)
            entites = []
            for annotation in cv["annotation"]:
                for p in annotation["points"]:
                    entites.append({"start": p["start"], "end": p["end"] + 1,
                                    "label": annotation["label"][0], "text": p["text"]})
            relations = {(r["type"], (r["tete"]["start"], r["tete"]["end"]),
                          (r["queue"]["start"], r["queue"]["end"])) for r in cv["relations"]}
            cvs.append({"texte": cv["content"], "entites": entites, "relations": relations})
    return cvs


def scores(predites, vraies):
    justes = len(predites & vraies)
    p = justes / len(predites) if predites else 0.0
    r = justes / len(vraies) if vraies else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def evaluer(cvs, methode, nlp, entites_de=None):
    """Compare les relations trouvées aux relations annotées, CV par CV."""
    toutes_predites, toutes_vraies, erreurs = set(), set(), []
    for n, cv in enumerate(cvs):
        entites = [dict(e) for e in (entites_de(cv) if entites_de else cv["entites"])]
        preparer(cv["texte"], entites)
        predites = methode(cv["texte"], entites, nlp)
        toutes_predites |= {(n,) + r for r in predites}
        toutes_vraies |= {(n,) + r for r in cv["relations"]}
        t = cv["texte"]
        for type_rel, (a, b), (c, d) in predites - cv["relations"]:
            erreurs.append({"cv": n, "erreur": "en trop", "type": type_rel,
                            "tete": t[a:b], "queue": t[c:d]})
        for type_rel, (a, b), (c, d) in cv["relations"] - predites:
            erreurs.append({"cv": n, "erreur": "manquée", "type": type_rel,
                            "tete": t[a:b], "queue": t[c:d]})
    global_ = scores(toutes_predites, toutes_vraies)
    par_type = {}
    for type_rel in sorted(set(TYPES.values())):
        par_type[type_rel] = scores({r for r in toutes_predites if r[1] == type_rel},
                                    {r for r in toutes_vraies if r[1] == type_rel})
    return global_, par_type, erreurs


def entites_predites_par(nlp_ner):
    def predire(cv):
        doc = nlp_ner(cv["texte"])
        return [{"start": e.start_char, "end": e.end_char, "label": e.label_, "text": e.text}
                for e in doc.ents]
    return predire


def graphique(resultats):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    noms = list(resultats)
    valeurs = [resultats[n][0][2] for n in noms]
    plt.figure(figsize=(8, 3.6))
    barres = plt.barh(noms[::-1], valeurs[::-1], color="tab:blue")
    for barre, v in zip(barres, valeurs[::-1]):
        plt.text(v + 0.01, barre.get_y() + barre.get_height() / 2, f"{v:.1%}", va="center")
    plt.xlim(0, 1.1)
    plt.xlabel("Score F sur la vérité terrain")
    plt.title("Extraction des relations : comparaison des techniques")
    plt.tight_layout()
    plt.savefig(os.path.join(DOSSIER_SORTIE, "comparaison_techniques.png"), dpi=120)


def ecrire_csv(chemin, lignes):
    if lignes:
        with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
            ecrivain = csv.DictWriter(f, fieldnames=lignes[0].keys(), delimiter=";")
            ecrivain.writeheader()
            ecrivain.writerows(lignes)


# ==============================================================
# APPLICATION : fiches des CV de la phase 2
# ==============================================================
def fiches_cv(nlp_ner, nlp, methode):
    fiches = {}
    for chemin in sorted(glob.glob(os.path.join(DOSSIER_TEXTES, "*.txt"))):
        texte = open(chemin, encoding="utf-8").read()
        entites = [{"start": e.start_char, "end": e.end_char, "label": e.label_, "text": e.text}
                   for e in nlp_ner(texte).ents]
        preparer(texte, entites)
        relations = methode(texte, entites, nlp)
        par_cle = {cle(e): e["text"] for e in entites}
        liens = {}
        for type_rel, tete, queue in relations:
            liens.setdefault(tete, {}).setdefault(type_rel, []).append(par_cle[queue])
        nom = next((e["text"] for e in entites if e["label"] == "NOM"), None)
        postes = [e for e in entites if e["label"] == "POSTE" and not e["en_tete"]]
        diplomes = [e for e in entites if e["label"] == "DIPLOME"]
        fiches[os.path.basename(chemin)] = {
            "nom": nom,
            "experiences": [{"poste": p["text"],
                             "entreprise": liens.get(cle(p), {}).get("EMPLOYEUR", []),
                             "periode": liens.get(cle(p), {}).get("PERIODE", [])} for p in postes],
            "formations": [{"diplome": d["text"],
                            "etablissement": liens.get(cle(d), {}).get("ECOLE", []),
                            "date": liens.get(cle(d), {}).get("OBTENU_EN", [])} for d in diplomes],
        }
    with open(os.path.join(DOSSIER_SORTIE, "fiches_cv.json"), "w", encoding="utf-8") as f:
        json.dump(fiches, f, ensure_ascii=False, indent=2)
    print("\n=== Fiches reconstruites à partir des CV de la phase 2 ===")
    for fichier, fiche in fiches.items():
        print(f"\n{fiche['nom']}  ({fichier})")
        for x in fiche["experiences"]:
            print(f"  Poste      {x['poste']:<32} chez {', '.join(x['entreprise']) or '?':<24}"
                  f" {' - '.join(x['periode'])}")
        for x in fiche["formations"]:
            print(f"  Diplôme    {x['diplome']:<32} à {', '.join(x['etablissement']) or '?':<26}"
                  f" {' '.join(x['date'])}")


# ==============================================================
# PROGRAMME PRINCIPAL
# ==============================================================
def main():
    import spacy

    os.makedirs(DOSSIER_SORTIE, exist_ok=True)
    print("=" * 66)
    print("1. TECHNIQUES D'EXTRACTION DE RELATIONS")
    print("=" * 66)
    print("  Co-occurrence : entités compatibles sur la même ligne")
    print("  Proximité     : tête compatible la plus proche dans le texte")
    print("  Dépendances   : tête compatible la plus proche dans l'arbre syntaxique")
    print("  + mise en page: date seule sur une ligne -> poste de la ligne du dessus")
    print("  (Autres techniques possibles : motifs lexicaux, apprentissage supervisé)\n")

    try:
        nlp = spacy.load("fr_core_news_sm")
    except OSError:
        print("Modèle absent -> python -m spacy download fr_core_news_sm")
        return
    demonstration(nlp, spacy)

    if not os.path.exists(FICHIER_RELATIONS):
        print(f"{FICHIER_RELATIONS} introuvable -> python generer_donnees_relations.py")
        return
    cvs = charger_verite_terrain(FICHIER_RELATIONS)
    nb_relations = sum(len(cv["relations"]) for cv in cvs)

    print("=" * 66)
    print(f"3. VALIDATION sur la vérité terrain : {len(cvs)} CV, {nb_relations} relations")
    print("=" * 66)
    print("a) Avec les entités exactes (on évalue seulement les relations)\n")
    print(f"{'Technique':<30}{'Précision':>10}{'Rappel':>9}{'Score F':>9}")
    resultats, lignes_csv = {}, []
    for nom, methode in METHODES.items():
        resultats[nom] = evaluer(cvs, methode, nlp)
        p, r, f = resultats[nom][0]
        print(f"{nom:<30}{p:>10.2%}{r:>9.2%}{f:>9.2%}")
        lignes_csv.append({"technique": nom, "precision": round(p, 4), "rappel": round(r, 4),
                           "score_f": round(f, 4)})
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "scores_techniques.csv"), lignes_csv)
    graphique(resultats)

    meilleure = max(resultats, key=lambda n: resultats[n][0][2])
    print(f"\nMeilleure technique : {meilleure}. Détail par type de relation :")
    print(f"{'Relation':<12}{'Précision':>10}{'Rappel':>9}{'Score F':>9}")
    lignes_csv = []
    for type_rel, (p, r, f) in resultats[meilleure][1].items():
        print(f"{type_rel:<12}{p:>10.2%}{r:>9.2%}{f:>9.2%}")
        lignes_csv.append({"relation": type_rel, "precision": round(p, 4),
                           "rappel": round(r, 4), "score_f": round(f, 4)})
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "scores_par_relation.csv"), lignes_csv)

    erreurs = resultats[meilleure][2]
    ecrire_csv(os.path.join(DOSSIER_SORTIE, "erreurs.csv"), erreurs)
    print(f"\nExemples d'erreurs ({len(erreurs)} au total) :")
    for e in erreurs[:8]:
        print(f"  {e['erreur']:<8} {e['type']:<10} {e['tete'][:28]!r} -> {e['queue'][:24]!r}")

    if not os.path.isdir(DOSSIER_MODELE_NER):
        print("\n(Modèle de la phase 3 absent : lancez phase3_ner.py pour l'évaluation complète.)")
        return
    from phase3_ner import ajouter_regles
    nlp_ner = ajouter_regles(spacy.load(DOSSIER_MODELE_NER))
    print("\nb) Système complet : entités prédites par le modèle de la phase 3")
    (p, r, f), _, _ = evaluer(cvs, METHODES[meilleure], nlp, entites_predites_par(nlp_ner))
    print(f"{meilleure:<30}{p:>10.2%}{r:>9.2%}{f:>9.2%}")
    print("Une relation n'est juste que si ses DEUX entités ont été trouvées exactement :")
    print("chaque erreur de la phase 3 se répercute sur la phase 4.")
    with open(os.path.join(DOSSIER_SORTIE, "systeme_complet.json"), "w", encoding="utf-8") as f_:
        json.dump({"technique": meilleure, "precision": p, "rappel": r, "score_f": f}, f_)

    fiches_cv(nlp_ner, nlp, METHODES[meilleure])
    print(f"\nRésultats enregistrés dans le dossier « {DOSSIER_SORTIE} »")


if __name__ == "__main__":
    main()
