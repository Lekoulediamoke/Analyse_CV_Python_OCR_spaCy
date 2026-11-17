# Présélection automatisée de CV de conseillers clientèle

Projet de certification : lire des CV (PDF, scans, photos, Word), en extraire les informations clés avec l'OCR et le traitement automatique du langage (spaCy), puis aider le recruteur à présélectionner les candidats.

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

## Installation

1. Installer **Tesseract OCR** pour Windows (installateur UB Mannheim), en cochant la langue **French** dans « Additional language data ».
2. Installer les bibliothèques Python :

```
python -m pip install -r requirements.txt
```

## Utilisation

```
python generer_cv_exemples.py
python phase1_extraction.py
```

Pour analyser un autre dossier : `python phase1_extraction.py mon_dossier_de_cv`

## Structure

| Fichier ou dossier | Rôle |
|---|---|
| `phase1_extraction.py` | Extraction des données (phase 1) |
| `generer_cv_exemples.py` | Création des CV fictifs de test |
| `cv_exemples/` | CV de test (4 formats) |
| `resultats/` | Informations extraites |
