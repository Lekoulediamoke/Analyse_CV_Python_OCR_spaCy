# Analyse de CV en apprentissage automatique avec Python, OCR et spaCy

Projet de certification, appliqué à la présélection de conseillers clientèle : lire des CV (PDF, scans, photos, Word), en extraire les informations clés avec l'OCR et le traitement automatique du langage (spaCy), puis aider le recruteur à présélectionner les candidats.

## Phase 1 : extraction des données

`phase1_extraction.py` traite tous les CV d'un dossier :

1. **Extraction du texte**
   - PDF numérique et Word : lecture directe du texte (`pdfplumber`, `python-docx`)
   - PDF scanné et photo : reconnaissance optique de caractères avec **Tesseract** (`pytesseract`), après amélioration de l'image (niveaux de gris, contraste, netteté, agrandissement)
2. **Prétraitement du texte** : normalisation des caractères, puces, espaces, mots coupés et bruit de l'OCR
3. **Extraction des informations** : nom, poste visé, e-mail, téléphone, formation et diplôme le plus élevé, expérience et nombre d'années, compétences, compétences clés du métier, langues
4. **Contrôle qualité** : confiance moyenne de l'OCR et colonne `a_verifier` qui signale les CV à relire par un humain (OCR peu fiable, champ manquant, e-mail reconstitué)
5. **Export** : `resultats/cv_extraits.csv` (Excel), `resultats/cv_extraits.json`, un JSON et un texte par CV

Les CV du dossier `cv_exemples/` sont **fictifs** (créés par `generer_cv_exemples.py`) et couvrent quatre formats : PDF numérique, PDF scanné, photo et Word.

## Phase 2 : nettoyage et normalisation

`phase2_nettoyage.py` reprend les résultats de la phase 1 :

1. **Bruit et informations non pertinentes** (expressions régulières) : symboles parasites de l'OCR, numéros de page, sections sans intérêt pour le recrutement (centres d'intérêt, références) et informations personnelles sources de discrimination (date de naissance, situation familiale, nationalité)
2. **Incohérences de formatage** : dates de formats variés (« Mars 2022 », « 03/2019 », « 2023 ») converties en `AAAA-MM` avec `dateutil`, années d'expérience recalculées en fusionnant les périodes qui se chevauchent, téléphones au format international, e-mails et noms unifiés, mots mal reconnus par l'OCR corrigés, compétences dédoublonnées, poste ramené à une catégorie standard
3. **Normalisation linguistique** : tokenisation et mots vides (spaCy), racinisation (NLTK) et lemmatisation (spaCy)

Sorties : `resultats/cv_nettoyes.csv` et `.json`, `resultats/journal_nettoyage.csv` (chaque correction avec sa valeur avant et après), `resultats/exemple_normalisation.csv` et `resultats/textes_nettoyes/`.

## Phase 3 : reconnaissance d'entités nommées (NER)

`phase3_ner.py` :

1. **Découverte** : le modèle français pré-entraîné de spaCy (`fr_core_news_sm`) appliqué aux CV nettoyés ; il ne reconnaît que les personnes, lieux et organisations
2. **Modèle personnalisé** : entraînement d'un modèle spaCy NER sur des CV annotés au format JSON du projet (étiquette, début, fin, texte). Le chargement corrige les défauts courants : fin d'entité incluse, espaces en bord d'entité, annotations qui se chevauchent, entités mal alignées sur les mots
3. **Évaluation** : précision, rappel et score F, globalement et par étiquette, analyse des erreurs, puis application aux CV de la phase 2

`generer_donnees_annotees.py` crée un jeu de 400 CV fictifs annotés (11 étiquettes : NOM, POSTE, VILLE, TELEPHONE, EMAIL, ENTREPRISE, DATE, DIPLOME, ETABLISSEMENT, COMPETENCE, LANGUE). Les CV de test utilisent des noms, entreprises, villes et établissements absents de l'entraînement. Pour utiliser un autre jeu annoté : `python phase3_ner.py mon_fichier.json`.

Sorties : `resultats_ner/` (scores, erreurs, entités trouvées, graphique) et le modèle dans `modele_ner/` (non versionné, recréé par le script).

## Phase 4 : extraction des relations

`phase4_relations.py` relie les entités entre elles : la personne et ses postes (A_OCCUPE), le poste et son entreprise (EMPLOYEUR) et ses dates (PERIODE), l'entreprise et sa ville (LIEU), le diplôme et son établissement (ECOLE) et sa date (OBTENU_EN).

1. **Techniques comparées** : co-occurrence sur la ligne, proximité dans le texte, analyse des dépendances syntaxiques (spaCy `fr_core_news_sm`), et règle de mise en page (dates écrites sous le poste)
2. **Analyse des dépendances** : exemple commenté sur une phrase à deux expériences, arbre dessiné dans `arbre_dependances.html`
3. **Validation** : précision, rappel et score F de chaque technique sur 150 CV annotés avec leurs relations (`generer_donnees_relations.py`), puis du système complet avec les entités prédites par le modèle de la phase 3 ; fiches reconstruites pour les CV de la phase 2

Sorties : `resultats_relations/`.

## Tests

`tester_projet.py` vérifie automatiquement les résultats de chaque phase sur les CV fictifs, dont le contenu est connu (e-mails, formats, années d'expérience, informations personnelles retirées, scores du modèle…). Il se lance après chaque phase et avant chaque envoi sur GitHub :

```
python tester_projet.py        # toutes les phases
python tester_projet.py 2      # une seule phase
```

## Installation

1. Installer **Tesseract OCR** pour Windows (installateur UB Mannheim), en cochant la langue **French** dans « Additional language data ».
2. Installer les bibliothèques Python :

```
python -m pip install -r requirements.txt
python -m spacy download fr_core_news_sm
```

## Utilisation

```
python generer_cv_exemples.py
python phase1_extraction.py
python phase2_nettoyage.py
python generer_donnees_annotees.py
python phase3_ner.py
python generer_donnees_relations.py
python phase4_relations.py
python tester_projet.py
```

Pour analyser un autre dossier : `python phase1_extraction.py mon_dossier_de_cv`

## Structure

| Fichier ou dossier | Rôle |
|---|---|
| `phase1_extraction.py` | Extraction des données (phase 1) |
| `phase2_nettoyage.py` | Nettoyage et normalisation (phase 2) |
| `generer_donnees_annotees.py` | Création du jeu de CV annotés |
| `generer_donnees_relations.py` | Création des CV annotés avec leurs relations |
| `phase4_relations.py` | Extraction des relations et validation (phase 4) |
| `tester_projet.py` | Tests automatiques de chaque phase |
| `phase3_ner.py` | Reconnaissance d'entités : entraînement et évaluation (phase 3) |
| `generer_cv_exemples.py` | Création des CV fictifs de test |
| `cv_exemples/` | CV de test (4 formats) |
| `resultats/` | Informations extraites |
