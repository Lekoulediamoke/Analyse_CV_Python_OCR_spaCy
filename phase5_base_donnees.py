# ==============================================================
# PHASE 5 - Intégration des données et modélisation
# Projet : Analyse de CV en apprentissage automatique avec Python, OCR et spaCy
#
# Les informations extraites aux phases précédentes sont rangées dans une
# base de données SQLite, interrogées en SQL, puis utilisées pour entraîner
# un modèle qui aide à la présélection des candidats.
#
# Quatre parties, comme dans les instructions :
#   1. Schéma de la base : candidats, expériences, formations, compétences…
#   2. Remplissage avec les informations extraites :
#        - les 4 CV d'exemple passés par tout le pipeline
#          (phase 2 : champs nettoyés, phase 4 : fiches avec les relations)
#        - 400 CV fictifs annotés (entités) reliés avec la technique de la phase 4
#      Les informations douteuses sont écartées et notées dans la table « rejets ».
#   3. Requêtes SQL et analyse de données de base
#   4. Apprentissage automatique : prédire si un candidat sera retenu pour un
#      entretien, à partir des décisions passées du recruteur (simulées ici),
#      puis classer les 4 candidats des CV d'exemple
#
# Usage : python phase5_base_donnees.py
# ==============================================================

import csv
import json
import math
import os
import random
import sqlite3

from phase2_nettoyage import (categorie_poste, cle, duree_totale_annees, lire_date,
                              normaliser_competences, normaliser_email, normaliser_nom,
                              normaliser_telephone)
from phase4_relations import METHODES, preparer

FICHIER_CV_FICTIFS = os.path.join("donnees", "cv_annotes.json")       # phase 3
FICHIER_CV_NETTOYES = os.path.join("resultats", "cv_nettoyes.json")    # phase 2
FICHIER_FICHES = os.path.join("resultats_relations", "fiches_cv.json")  # phase 4
TECHNIQUE_RELATIONS = "Proximité + mise en page"    # meilleure technique de la phase 4
DOSSIER_SORTIE = "resultats_bdd"
BASE = os.path.join(DOSSIER_SORTIE, "base_cv.db")

POSTES_RELATION_CLIENT = ("Conseiller clientèle", "Téléconseiller", "Chargé de clientèle")
COMPETENCES_RELATIONNELLES = ("relation client", "ecoute active", "gestion des reclamations",
                              "fidelisation", "gestion du stress", "gestion des appels entrants",
                              "appels entrants", "travail en equipe", "communication",
                              "service apres vente")
OUTILS_CRM = ("crm", "salesforce", "zendesk", "freshdesk", "hubspot")


# ==============================================================
# 1. SCHÉMA DE LA BASE DE DONNÉES
# ==============================================================
SCHEMA = """
-- Un candidat = un CV
CREATE TABLE candidats (
    id                INTEGER PRIMARY KEY,
    nom               TEXT NOT NULL,
    email             TEXT,
    telephone         TEXT,
    ville             TEXT,
    poste_vise        TEXT,
    categorie_poste   TEXT,
    niveau_etudes     INTEGER,          -- années d'études après le bac (Licence = 3)
    annees_experience REAL,
    source            TEXT NOT NULL CHECK (source IN ('exemple', 'fictif')),
    fichier           TEXT
);

-- Un candidat a 0, 1 ou plusieurs expériences (relations EMPLOYEUR, PERIODE, LIEU)
CREATE TABLE experiences (
    id              INTEGER PRIMARY KEY,
    candidat_id     INTEGER NOT NULL REFERENCES candidats(id) ON DELETE CASCADE,
    poste           TEXT NOT NULL,
    categorie_poste TEXT,
    entreprise      TEXT,
    ville           TEXT,
    date_debut      TEXT,               -- AAAA-MM
    date_fin        TEXT,
    duree_mois      INTEGER
);

-- Un candidat a 0, 1 ou plusieurs diplômes (relations ECOLE, OBTENU_EN)
CREATE TABLE formations (
    id            INTEGER PRIMARY KEY,
    candidat_id   INTEGER NOT NULL REFERENCES candidats(id) ON DELETE CASCADE,
    diplome       TEXT NOT NULL,
    niveau        INTEGER,
    etablissement TEXT,
    annee         INTEGER
);

-- Chaque compétence ou langue n'est enregistrée qu'une fois...
CREATE TABLE competences (
    id      INTEGER PRIMARY KEY,
    libelle TEXT NOT NULL,
    cle     TEXT NOT NULL,              -- minuscules sans accents, pour éviter les doublons
    type    TEXT NOT NULL CHECK (type IN ('metier', 'langue')),
    UNIQUE (cle, type)
);

-- ... et reliée aux candidats par une table d'association (relation plusieurs à plusieurs)
CREATE TABLE candidat_competences (
    candidat_id   INTEGER NOT NULL REFERENCES candidats(id) ON DELETE CASCADE,
    competence_id INTEGER NOT NULL REFERENCES competences(id),
    PRIMARY KEY (candidat_id, competence_id)
);

-- Informations écartées au contrôle qualité, pour relecture humaine
CREATE TABLE rejets (
    id          INTEGER PRIMARY KEY,
    candidat_id INTEGER NOT NULL REFERENCES candidats(id) ON DELETE CASCADE,
    champ       TEXT,
    valeur      TEXT,
    motif       TEXT
);

-- Décisions passées du recruteur (1 = retenu pour un entretien)
CREATE TABLE decisions (
    candidat_id INTEGER PRIMARY KEY REFERENCES candidats(id) ON DELETE CASCADE,
    retenu      INTEGER NOT NULL CHECK (retenu IN (0, 1))
);

-- Prédictions du modèle pour les nouvelles candidatures
CREATE TABLE predictions (
    candidat_id INTEGER PRIMARY KEY REFERENCES candidats(id) ON DELETE CASCADE,
    modele      TEXT,
    probabilite REAL,
    rang        INTEGER
);

CREATE INDEX idx_experiences_candidat ON experiences(candidat_id);
CREATE INDEX idx_formations_candidat ON formations(candidat_id);
CREATE INDEX idx_competences_candidat ON candidat_competences(candidat_id);
"""


def creer_base():
    os.makedirs(DOSSIER_SORTIE, exist_ok=True)
    if os.path.exists(BASE):
        os.remove(BASE)                       # la base est reconstruite à chaque lancement
    con = sqlite3.connect(BASE)
    con.execute("PRAGMA foreign_keys = ON")   # SQLite ne vérifie les clés étrangères que sur demande
    con.executescript(SCHEMA)
    with open(os.path.join(DOSSIER_SORTIE, "schema.sql"), "w", encoding="utf-8") as f:
        f.write(SCHEMA.strip() + "\n")
    return con


# ==============================================================
# 2. REMPLISSAGE AVEC LES INFORMATIONS EXTRAITES
# ==============================================================
def niveau_diplome(diplome):
    """Nombre d'années d'études après le bac, ou None si le diplôme est inconnu."""
    k = cle(diplome or "")
    for motif, niveau in (("doctorat", 8), ("master 1", 4), ("master", 5), ("licence", 3),
                          ("bts", 2), ("dut", 2), ("dts", 2), ("bac", 0)):
        if motif in k:
            return niveau
    return None


def lire(texte, fin=False):
    try:
        return lire_date(texte.strip(), fin_de_periode=fin)
    except (ValueError, OverflowError, AttributeError):
        return None


def periode(dates):
    """[« Mars 2022 », « 2024 »] -> (début, fin). Une seule date : poste en cours."""
    lues = sorted((d, t) for t in dates if (d := lire(t)))
    if not lues:
        return None, None
    debut = lues[0][0]
    fin = lire(lues[-1][1], fin=True) if len(lues) > 1 else lire("présent")
    return debut, fin


def mois_entre(debut, fin):
    return (fin.year - debut.year) * 12 + fin.month - debut.month + 1


class Integrateur:
    """Ajoute les candidats dans la base en appliquant les mêmes règles de
    contrôle, quelle que soit l'origine des données."""

    def __init__(self, con):
        self.con = con
        self.ids_competences = {}

    def candidat(self, **champs):
        colonnes = ", ".join(champs)
        marques = ", ".join("?" for _ in champs)
        cur = self.con.execute(f"INSERT INTO candidats ({colonnes}) VALUES ({marques})",
                               list(champs.values()))
        return cur.lastrowid

    def rejeter(self, cid, champ, valeur, motif):
        self.con.execute("INSERT INTO rejets (candidat_id, champ, valeur, motif) VALUES (?, ?, ?, ?)",
                         (cid, champ, valeur, motif))

    def experience(self, cid, poste, entreprise, ville, dates):
        """Renvoie la période retenue (pour le calcul des années d'expérience)."""
        if len(poste.split()) > 6:
            self.rejeter(cid, "poste", poste, "trop long pour un intitulé (phrase de profil ?)")
            return None
        debut, fin = periode(dates)
        self.con.execute(
            "INSERT INTO experiences (candidat_id, poste, categorie_poste, entreprise, ville,"
            " date_debut, date_fin, duree_mois) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, poste, categorie_poste(poste), entreprise, ville,
             debut and f"{debut:%Y-%m}", fin and f"{fin:%Y-%m}", debut and mois_entre(debut, fin)))
        return (debut, fin) if debut else None

    def formation(self, cid, diplome, etablissement, date):
        niveau = niveau_diplome(diplome)
        if niveau is None:
            self.rejeter(cid, "diplome", diplome, "diplôme non reconnu")
            return None
        d = lire(date) if date else None
        self.con.execute("INSERT INTO formations (candidat_id, diplome, niveau, etablissement, annee)"
                         " VALUES (?, ?, ?, ?, ?)", (cid, diplome, niveau, etablissement, d and d.year))
        return niveau

    def competences(self, cid, libelles, type_):
        for libelle in libelles:
            k = cle(libelle)
            if not k:
                continue
            if (k, type_) not in self.ids_competences:
                cur = self.con.execute("INSERT INTO competences (libelle, cle, type) VALUES (?, ?, ?)",
                                       (libelle, k, type_))
                self.ids_competences[(k, type_)] = cur.lastrowid
            self.con.execute("INSERT OR IGNORE INTO candidat_competences VALUES (?, ?)",
                             (cid, self.ids_competences[(k, type_)]))


def integrer_cv_exemples(integ):
    """Les 4 CV d'exemple : champs de la phase 2 + expériences et formations
    reliées par la phase 4."""
    if not os.path.exists(FICHIER_CV_NETTOYES):
        print(f"  {FICHIER_CV_NETTOYES} introuvable -> lancez phase2_nettoyage.py")
        return 0
    cvs = json.load(open(FICHIER_CV_NETTOYES, encoding="utf-8"))
    fiches = {}
    if os.path.exists(FICHIER_FICHES):
        fiches = json.load(open(FICHIER_FICHES, encoding="utf-8"))
    else:
        print(f"  {FICHIER_FICHES} introuvable -> lancez phase4_relations.py")
    for cv in cvs:
        cid = integ.candidat(nom=cv["nom"], email=cv["email"], telephone=cv["telephone"],
                             poste_vise=cv["poste_vise"], categorie_poste=cv["categorie_poste"],
                             niveau_etudes=cv["niveau_bac_plus"],
                             annees_experience=cv["annees_experience"],
                             source="exemple", fichier=cv["fichier"])
        fiche = fiches.get(os.path.splitext(cv["fichier"])[0] + ".txt", {})
        for x in fiche.get("experiences", []):
            integ.experience(cid, x["poste"], ", ".join(x["entreprise"]) or None, None, x["periode"])
        niveaux = [integ.formation(cid, x["diplome"], ", ".join(x["etablissement"]) or None,
                                   (x["date"] or [None])[0]) for x in fiche.get("formations", [])]
        niveaux = [n for n in niveaux if n is not None]
        if niveaux and max(niveaux) != cv["niveau_bac_plus"]:
            # Les diplômes détaillés (phase 4) sont plus précis que la phase 2
            # (ex. « Master 1 » = Bac+4, et non Bac+5)
            integ.con.execute("UPDATE candidats SET niveau_etudes = ? WHERE id = ?", (max(niveaux), cid))
            integ.rejeter(cid, "niveau_etudes", f"Bac+{cv['niveau_bac_plus']}",
                          f"corrigé en Bac+{max(niveaux)} d'après les diplômes")
        integ.competences(cid, cv["competences"], "metier")
        integ.competences(cid, cv["langues"], "langue")
    return len(cvs)


def charger_entites(cv):
    """Entités annotées, corrigées des défauts connus (espaces, chevauchements)."""
    texte, entites, occupe = cv["content"], [], set()
    points = [(a["label"][0], p) for a in cv["annotation"] for p in a["points"]]
    for etiquette, p in points:
        debut, fin = p["start"], p["end"] + 1          # fin incluse dans le format du projet
        while debut < fin and texte[debut].isspace():
            debut += 1
        while fin > debut and texte[fin - 1].isspace():
            fin -= 1
        if debut == fin or occupe & set(range(debut, fin)):
            continue
        occupe |= set(range(debut, fin))
        entites.append({"start": debut, "end": fin, "label": etiquette, "text": texte[debut:fin]})
    return sorted(entites, key=lambda e: e["start"])


def integrer_cv_fictifs(integ):
    """400 CV fictifs : entités annotées, relations trouvées par la phase 4."""
    if not os.path.exists(FICHIER_CV_FICTIFS):
        print(f"  {FICHIER_CV_FICTIFS} introuvable -> lancez generer_donnees_annotees.py")
        return 0
    methode = METHODES[TECHNIQUE_RELATIONS]
    n = 0
    for n, ligne in enumerate(open(FICHIER_CV_FICTIFS, encoding="utf-8"), 1):
        cv = json.loads(ligne)
        texte, entites = cv["content"], charger_entites(cv)
        preparer(texte, entites)
        liens = {}
        for type_rel, tete, queue in methode(texte, entites, None):
            liens.setdefault((tete, type_rel), []).append(queue)
        par_cle = {(e["start"], e["end"]): e for e in entites}
        lies = lambda e, t: [par_cle[q] for q in liens.get(((e["start"], e["end"]), t), [])]
        premier = lambda e, t: next((x["text"] for x in lies(e, t)), None)
        en_tete = lambda etiquette: next((e["text"] for e in entites
                                          if e["label"] == etiquette and e["en_tete"]), None)

        poste_vise = en_tete("POSTE")
        email, _, _ = normaliser_email(en_tete("EMAIL"))
        telephone, _ = normaliser_telephone(en_tete("TELEPHONE"))
        cid = integ.candidat(nom=normaliser_nom(en_tete("NOM")), email=email, telephone=telephone,
                             ville=en_tete("VILLE"), poste_vise=poste_vise,
                             categorie_poste=categorie_poste(poste_vise),
                             source="fictif", fichier=f"cv_annotes.json:{n}")
        periodes, niveaux = [], []
        for e in entites:
            if e["en_tete"]:
                continue
            if e["label"] == "POSTE":
                entreprises = lies(e, "EMPLOYEUR")
                ville = premier(entreprises[0], "LIEU") if entreprises else None
                p = integ.experience(cid, e["text"], entreprises[0]["text"] if entreprises else None,
                                     ville, [x["text"] for x in lies(e, "PERIODE")])
                if p:
                    periodes.append(p)
            elif e["label"] == "DIPLOME":
                niveau = integ.formation(cid, e["text"], premier(e, "ECOLE"), premier(e, "OBTENU_EN"))
                if niveau is not None:
                    niveaux.append(niveau)
        integ.con.execute("UPDATE candidats SET niveau_etudes = ?, annees_experience = ? WHERE id = ?",
                          (max(niveaux) if niveaux else None,
                           duree_totale_annees(periodes) if periodes else 0.0, cid))
        integ.competences(cid, normaliser_competences(
            [e["text"] for e in entites if e["label"] == "COMPETENCE"], f"cv_{n}"), "metier")
        integ.competences(cid, [e["text"] for e in entites if e["label"] == "LANGUE"], "langue")
    return n


# Variables décrivant chaque candidat, calculées EN SQL à partir des tables
def _compter(condition):
    return (f"(SELECT COUNT(*) FROM candidat_competences cc JOIN competences k "
            f"ON k.id = cc.competence_id WHERE cc.candidat_id = c.id AND {condition})")


def _liste(valeurs):
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in valeurs) + ")"


REQUETE_VARIABLES = f"""
SELECT c.id, c.nom, c.source,
       c.annees_experience,
       c.niveau_etudes,
       (SELECT COUNT(*) FROM experiences e WHERE e.candidat_id = c.id) AS nb_experiences,
       (SELECT COUNT(*) FROM experiences e WHERE e.candidat_id = c.id
            AND e.categorie_poste IN {_liste(POSTES_RELATION_CLIENT)}) AS postes_relation_client,
       {_compter("k.type = 'metier'")} AS nb_competences,
       {_compter("k.cle IN " + _liste(COMPETENCES_RELATIONNELLES))} AS competences_relationnelles,
       {_compter("k.cle IN " + _liste(OUTILS_CRM))} AS outils_crm,
       {_compter("k.type = 'langue'")} AS nb_langues,
       {_compter("k.type = 'langue' AND k.cle = 'anglais'")} AS anglais
FROM candidats c
ORDER BY c.id
"""
VARIABLES = ["annees_experience", "niveau_etudes", "nb_experiences", "postes_relation_client",
             "nb_competences", "competences_relationnelles", "outils_crm", "nb_langues", "anglais"]


def simuler_decisions(con, pd):
    """Les CV fictifs n'ont pas d'historique : on simule les décisions passées
    d'un recruteur, avec une grille cachée ET une part de hasard (un recruteur
    n'est pas parfaitement régulier). En entreprise, on utiliserait les vraies
    décisions des campagnes précédentes."""
    rng = random.Random(5)
    df = pd.read_sql_query(REQUETE_VARIABLES, con)
    for _, c in df[df.source == "fictif"].iterrows():
        niveau = 0 if pd.isna(c.niveau_etudes) else c.niveau_etudes
        z = (-4.2 + 0.45 * min(c.annees_experience, 8) + 0.7 * min(c.postes_relation_client, 2)
             + 0.35 * c.competences_relationnelles + 0.6 * min(c.outils_crm, 1)
             + 1.1 * c.anglais + 0.12 * niveau)
        retenu = int(rng.random() < 1 / (1 + math.exp(-z)))
        con.execute("INSERT INTO decisions VALUES (?, ?)", (int(c.id), retenu))


# ==============================================================
# 3. REQUÊTES SQL ET ANALYSE DE DONNÉES DE BASE
# ==============================================================
ANGLAIS = ("EXISTS (SELECT 1 FROM candidat_competences cc JOIN competences k ON k.id = cc.competence_id"
           " WHERE cc.candidat_id = c.id AND k.type = 'langue' AND k.cle = 'anglais')")
REQUETES = {
    "Contenu de la base": """
SELECT 'candidats' AS table_, COUNT(*) AS lignes FROM candidats
UNION ALL SELECT 'experiences', COUNT(*) FROM experiences
UNION ALL SELECT 'formations', COUNT(*) FROM formations
UNION ALL SELECT 'competences', COUNT(*) FROM competences
UNION ALL SELECT 'candidat_competences', COUNT(*) FROM candidat_competences
UNION ALL SELECT 'rejets', COUNT(*) FROM rejets
UNION ALL SELECT 'decisions', COUNT(*) FROM decisions""",

    "Les 10 compétences métier les plus citées": """
SELECT k.libelle AS competence, COUNT(*) AS candidats
FROM candidat_competences cc
JOIN competences k ON k.id = cc.competence_id
WHERE k.type = 'metier'
GROUP BY k.id
ORDER BY candidats DESC, competence
LIMIT 10""",

    "Expérience moyenne selon le niveau d'études": """
SELECT niveau_etudes AS bac_plus, COUNT(*) AS candidats,
       ROUND(AVG(annees_experience), 1) AS experience_moyenne_ans
FROM candidats
WHERE niveau_etudes IS NOT NULL
GROUP BY niveau_etudes
ORDER BY niveau_etudes""",

    "Les 5 employeurs les plus fréquents": """
SELECT entreprise, COUNT(DISTINCT candidat_id) AS candidats,
       ROUND(AVG(duree_mois)) AS duree_moyenne_mois
FROM experiences
WHERE entreprise IS NOT NULL
GROUP BY entreprise
ORDER BY candidats DESC, entreprise
LIMIT 5""",

    "Présélection par critères : 2 ans d'expérience, anglais, déjà en relation client": f"""
SELECT c.nom, c.source, c.annees_experience AS experience_ans,
       COUNT(*) OVER () AS total_candidats_trouves
FROM candidats c
WHERE c.annees_experience >= 2
  AND {ANGLAIS}
  AND EXISTS (SELECT 1 FROM experiences e WHERE e.candidat_id = c.id
              AND e.categorie_poste IN {_liste(POSTES_RELATION_CLIENT)})
ORDER BY c.annees_experience DESC
LIMIT 8""",

    "Décisions passées : taux de candidats retenus selon l'anglais": f"""
SELECT CASE WHEN {ANGLAIS} THEN 'parle anglais' ELSE 'sans anglais' END AS groupe,
       COUNT(*) AS candidats, ROUND(100.0 * AVG(d.retenu), 1) AS pourcentage_retenus
FROM candidats c
JOIN decisions d ON d.candidat_id = c.id
GROUP BY groupe""",

    "Contrôle qualité : informations écartées ou corrigées à l'intégration": """
SELECT c.nom, r.champ, r.valeur, r.motif
FROM rejets r
JOIN candidats c ON c.id = r.candidat_id
ORDER BY c.id""",
}


def requetes_sql(con, pd):
    print("=" * 66)
    print("3. REQUÊTES SQL ET ANALYSE DE DONNÉES")
    print("=" * 66)
    with open(os.path.join(DOSSIER_SORTIE, "requetes.sql"), "w", encoding="utf-8") as f:
        for titre, sql in REQUETES.items():
            f.write(f"-- {titre}{sql};\n\n")
    for titre, sql in REQUETES.items():
        resultat = pd.read_sql_query(sql, con)
        print(f"\n--- {titre}")
        print(resultat.to_string(index=False, max_colwidth=45))
    print(f"\nRequêtes enregistrées dans {DOSSIER_SORTIE}/requetes.sql")


def graphiques_analyse(con, pd, plt):
    df = pd.read_sql_query(REQUETE_VARIABLES, con).merge(
        pd.read_sql_query("SELECT * FROM decisions", con), left_on="id", right_on="candidat_id")
    df["tranche"] = pd.cut(df.annees_experience, [-0.1, 2, 4, 6, 100],
                           labels=["moins de 2 ans", "2 à 4 ans", "4 à 6 ans", "plus de 6 ans"])
    taux = df.groupby("tranche", observed=False).retenu.mean() * 100
    top = pd.read_sql_query(REQUETES["Les 10 compétences métier les plus citées"], con)

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.8))
    a.bar(taux.index.astype(str), taux.values, color="tab:blue")
    for i, v in enumerate(taux.values):
        a.text(i, v + 1, f"{v:.0f} %", ha="center")
    a.set_ylabel("% retenus pour un entretien")
    a.set_ylim(0, max(taux.values) + 12)
    a.set_title("Décisions passées selon l'expérience")
    b.barh(top.competence[::-1], top.candidats[::-1], color="tab:blue")
    b.set_xlabel("Nombre de candidats")
    b.set_title("Compétences métier les plus citées")
    fig.tight_layout()
    fig.savefig(os.path.join(DOSSIER_SORTIE, "analyse_donnees.png"), dpi=120)
    plt.close(fig)


# ==============================================================
# 4. APPRENTISSAGE AUTOMATIQUE : AIDE À LA PRÉSÉLECTION
# ==============================================================
def modelisation(con, pd, plt):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score)
    from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeClassifier

    print("\n" + "=" * 66)
    print("4. APPRENTISSAGE AUTOMATIQUE : qui sera retenu pour un entretien ?")
    print("=" * 66)
    df = pd.read_sql_query(REQUETE_VARIABLES, con)
    decisions = pd.read_sql_query("SELECT * FROM decisions", con)
    histo = df.merge(decisions, left_on="id", right_on="candidat_id")
    X, y = histo[VARIABLES], histo.retenu
    print(f"Données : {len(histo)} candidatures passées, {y.mean():.0%} retenues ; "
          f"{len(VARIABLES)} variables calculées en SQL")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y,
                                                        random_state=42)
    modeles = {
        "Régression logistique": LogisticRegression(max_iter=1000),
        "Arbre de décision": DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, random_state=42),
        "Forêt aléatoire": RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
                                                  random_state=42),
    }
    plis = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    print(f"\n{'Modèle':<24}{'AUC (valid. croisée)':>21}{'Exactitude':>12}{'Précision':>11}"
          f"{'Rappel':>8}{'F1':>7}{'AUC':>7}")
    lignes, pipelines = [], {}
    for nom, modele in modeles.items():
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), modele)
        auc_cv = cross_val_score(pipe, X_train, y_train, cv=plis, scoring="roc_auc")
        pipe.fit(X_train, y_train)
        prevu = pipe.predict(X_test)
        proba = pipe.predict_proba(X_test)[:, 1]
        ligne = {"modele": nom, "auc_validation_croisee": round(auc_cv.mean(), 4),
                 "ecart_type": round(auc_cv.std(), 4),
                 "exactitude": round(accuracy_score(y_test, prevu), 4),
                 "precision": round(precision_score(y_test, prevu), 4),
                 "rappel": round(recall_score(y_test, prevu), 4),
                 "f1": round(f1_score(y_test, prevu), 4),
                 "auc": round(roc_auc_score(y_test, proba), 4)}
        lignes.append(ligne)
        pipelines[nom] = pipe
        print(f"{nom:<24}{auc_cv.mean():>14.3f} ± {auc_cv.std():.3f}{ligne['exactitude']:>12.1%}"
              f"{ligne['precision']:>11.1%}{ligne['rappel']:>8.1%}{ligne['f1']:>7.1%}"
              f"{ligne['auc']:>7.3f}")
    with open(os.path.join(DOSSIER_SORTIE, "scores_modeles.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        ecrivain = csv.DictWriter(f, fieldnames=lignes[0].keys(), delimiter=";")
        ecrivain.writeheader()
        ecrivain.writerows(lignes)

    # Choix du modèle sur la validation croisée (pas sur le test, pour rester honnête)
    meilleur = max(lignes, key=lambda l: l["auc_validation_croisee"])["modele"]
    pipe = pipelines[meilleur]
    print(f"\nModèle retenu (meilleure AUC en validation croisée) : {meilleur}")
    vn, fp, fn, vp = confusion_matrix(y_test, pipe.predict(X_test)).ravel()
    print(f"Matrice de confusion sur le test : {vp} retenus bien prédits, {vn} refus bien prédits,"
          f" {fp} faux retenus, {fn} retenus manqués")

    # Ce qui pèse dans la décision : importance par permutation
    imp = permutation_importance(pipe, X_test, y_test, scoring="roc_auc", n_repeats=20,
                                 random_state=42)
    importance = pd.Series(imp.importances_mean, index=VARIABLES).sort_values()
    print("\nCe qui pèse le plus (perte d'AUC si l'on mélange la variable) :")
    for variable, valeur in importance[::-1].items():
        print(f"  {variable:<28}{valeur:>7.3f}")
    plt.figure(figsize=(7, 3.8))
    plt.barh(importance.index, importance.values, color="tab:blue")
    plt.xlabel("Perte d'AUC quand la variable est mélangée")
    plt.title(f"Critères qui expliquent les décisions ({meilleur})")
    plt.tight_layout()
    plt.savefig(os.path.join(DOSSIER_SORTIE, "importance_criteres.png"), dpi=120)
    plt.close()

    # Prédiction pour les nouvelles candidatures (les 4 CV d'exemple)
    pipe.fit(X, y)                       # réentraîné sur tout l'historique
    nouveaux = df[df.source == "exemple"].copy()
    if nouveaux.empty:
        return
    nouveaux["probabilite"] = pipe.predict_proba(nouveaux[VARIABLES])[:, 1]
    nouveaux = nouveaux.sort_values("probabilite", ascending=False)
    print("\n=== Classement des nouvelles candidatures (CV d'exemple) ===")
    print(f"{'Rang':<6}{'Candidat':<18}{'Proba. retenu':>14}{'Exp.':>7}{'Bac+':>6}"
          f"{'Postes RC':>11}{'Anglais':>9}")
    for rang, (_, c) in enumerate(nouveaux.iterrows(), 1):
        con.execute("INSERT INTO predictions VALUES (?, ?, ?, ?)",
                    (int(c.id), meilleur, round(float(c.probabilite), 4), rang))
        niveau = "-" if pd.isna(c.niveau_etudes) else int(c.niveau_etudes)
        print(f"{rang:<6}{c.nom:<18}{c.probabilite:>14.0%}{c.annees_experience:>7.1f}"
              f"{niveau:>6}{c.postes_relation_client:>11}{'oui' if c.anglais else 'non':>9}")
    con.commit()
    print("Le modèle propose un ordre de lecture : la décision finale reste au recruteur.")


# ==============================================================
# PROGRAMME PRINCIPAL
# ==============================================================
def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    print("=" * 66)
    print("1. SCHÉMA DE LA BASE DE DONNÉES (SQLite)")
    print("=" * 66)
    con = creer_base()
    tables = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    print(f"Base {BASE} créée : {len(tables)} tables")
    print("  " + ", ".join(tables))
    print(f"Schéma complet : {DOSSIER_SORTIE}/schema.sql\n")

    print("=" * 66)
    print("2. REMPLISSAGE AVEC LES INFORMATIONS EXTRAITES")
    print("=" * 66)
    integ = Integrateur(con)
    n_exemples = integrer_cv_exemples(integ)
    print(f"  {n_exemples} CV d'exemple (phases 1 à 4 : champs nettoyés + relations)")
    n_fictifs = integrer_cv_fictifs(integ)
    print(f"  {n_fictifs} CV fictifs (entités annotées + relations « {TECHNIQUE_RELATIONS} »)")
    simuler_decisions(con, pd)
    con.commit()
    n_rejets = con.execute("SELECT COUNT(*) FROM rejets").fetchone()[0]
    erreurs_cles = con.execute("PRAGMA foreign_key_check").fetchall()
    print(f"  {n_rejets} informations écartées ou corrigées au contrôle qualité (table « rejets »)")
    print(f"  Intégrité des clés étrangères : {'OK' if not erreurs_cles else erreurs_cles}")
    print("  Décisions passées du recruteur : simulées pour les CV fictifs (table « decisions »)\n")

    requetes_sql(con, pd)
    graphiques_analyse(con, pd, plt)
    modelisation(con, pd, plt)
    con.close()
    print(f"\nRésultats enregistrés dans le dossier « {DOSSIER_SORTIE} »")


if __name__ == "__main__":
    main()
