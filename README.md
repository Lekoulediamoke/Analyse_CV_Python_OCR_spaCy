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
```

Pour analyser un autre dossier : `python phase1_extraction.py mon_dossier_de_cv`

## Structure

| Fichier ou dossier | Rôle |
|---|---|
| `phase1_extraction.py` | Extraction des données (phase 1) |
| `phase2_nettoyage.py` | Nettoyage et normalisation (phase 2) |
| `generer_cv_exemples.py` | Création des CV fictifs de test |
| `cv_exemples/` | CV de test (4 formats) |
| `resultats/` | Informations extraites |
