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
