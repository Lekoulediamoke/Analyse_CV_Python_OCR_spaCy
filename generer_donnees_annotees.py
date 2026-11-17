# ==============================================================
# Génère un jeu de CV ANNOTÉS (fictifs) pour entraîner le modèle NER
#
# Format identique à celui décrit dans le projet : un document JSON par
# ligne, avec le texte du CV et, pour chaque entité, son étiquette, sa
# position de début, sa position de fin et son texte :
#   {"content": "...", "annotation": [{"label": ["NOM"],
#     "points": [{"start": 0, "end": 13, "text": "Aminata Ndiaye"}]}], "extras": {...}}
# (comme dans le jeu de données d'origine, "end" est INCLUS)
#
# Pour une évaluation honnête, les CV de test utilisent des noms,
# entreprises, villes et écoles qui n'apparaissent JAMAIS dans les CV
# d'entraînement : le modèle doit généraliser, pas apprendre des listes.
#
# Quelques défauts volontaires imitent les données réelles : espaces en
# trop autour d'une entité, annotation en double qui chevauche une autre.
#
# Usage : python generer_donnees_annotees.py
# ==============================================================

import json
import os
import random

random.seed(7)
NB_CV = 400
PART_TEST = 0.2

PRENOMS = ["Aminata", "Awa", "Fatou", "Mariama", "Khady", "Ndeye", "Aïssatou", "Coumba",
           "Rokhaya", "Bineta", "Astou", "Seynabou", "Marième", "Adama", "Sokhna", "Dieynaba",
           "Moussa", "Ibrahima", "Mamadou", "Cheikh", "Ousmane", "Abdoulaye", "Modou", "Pape",
           "Serigne", "Babacar", "Lamine", "Alioune", "Omar", "Saliou", "Malick", "Youssou",
           "Sophie", "Julie", "Camille", "Thomas", "Nicolas", "Karim", "Yasmine", "Nadia"]
NOMS = ["Ndiaye", "Diop", "Fall", "Sarr", "Ba", "Sow", "Gueye", "Faye", "Diallo", "Mbaye",
        "Cissé", "Seck", "Thiam", "Kane", "Ndour", "Diouf", "Sy", "Niang", "Camara", "Touré",
        "Sène", "Wade", "Dieng", "Mbengue", "Lo", "Badji", "Sagna", "Dramé", "Martin", "Bernard",
        "Petit", "Moreau", "Laurent", "Benali", "Haddad"]
VILLES = ["Dakar", "Thiès", "Saint-Louis", "Rufisque", "Pikine", "Guédiawaye", "Mbour",
          "Kaolack", "Ziguinchor", "Touba", "Louga", "Diourbel", "Tambacounda", "Kolda",
          "Abidjan", "Bamako", "Paris", "Lyon", "Casablanca", "Nouakchott"]
ENTREPRISES = ["TéléServices Afrique", "Callmax Sénégal", "Orbis Télécom", "Centre d'Appels Horizon",
               "Phone Services Dakar", "Crédit Express", "Distribution Plus", "Atlantique Contact",
               "Teranga Call Center", "Sahel Relation Client", "Baobab Services", "Océan Télécom",
               "Afrique Outsourcing", "Kora Contact", "Dakar Assistance", "Vision Clients",
               "Ndar Télécom", "Sunu Banque", "Liberté Assurances", "Senelec Services",
               "MediaCall", "Global Contact", "Wari Connect", "Jappo Services",
               "Cap Vert Assistance", "Nouvelle Énergie Distribution"]
ETABLISSEMENTS = ["Université Cheikh Anta Diop", "Université Gaston Berger", "ISM Dakar",
                  "IUT de Dakar", "Université Alioune Diop", "Université Iba Der Thiam",
                  "Sup de Co Dakar", "BEM Dakar", "IAM Dakar", "ESP Dakar", "Lycée Blaise Diagne",
                  "Lycée Lamine Guèye", "Lycée Seydou Nourou Tall", "Université Assane Seck",
                  "Institut Supérieur de Management", "École Supérieure Polytechnique",
                  "ENSUP Afrique", "Université Virtuelle du Sénégal", "Lycée Limamoulaye",
                  "CESAG"]
DIPLOMES = ["Master en Marketing", "Master Gestion des Ressources Humaines", "Master 1 Commerce",
            "Licence en Gestion des Entreprises", "Licence en Communication", "Licence Économie",
            "Licence professionnelle Relation Client", "BTS Communication d'entreprise",
            "BTS Action Commerciale", "BTS Assistant de Direction", "DUT Techniques de commercialisation",
            "DUT Gestion", "Baccalauréat série L", "Baccalauréat série G", "Baccalauréat série S2",
            "DTS Relation Client"]
POSTES = ["Conseillère clientèle", "Conseiller clientèle", "Téléconseillère", "Téléconseiller",
          "Chargée de clientèle", "Chargé de clientèle", "Agent de recouvrement",
          "Conseiller commercial", "Agent d'accueil", "Superviseur centre d'appels",
          "Conseillère clientèle bilingue", "Téléopérateur", "Agent service client",
          "Conseiller technique niveau 1", "Télévendeuse"]
COMPETENCES = ["relation client", "écoute active", "gestion des réclamations", "vente additionnelle",
               "fidélisation", "Salesforce", "Zendesk", "Pack Office", "Excel", "négociation",
               "prospection", "gestion des appels entrants", "appels sortants", "recouvrement",
               "assistance technique", "gestion du stress", "travail en équipe", "CRM",
               "communication écrite", "service après-vente", "prise de notes", "Freshdesk",
               "HubSpot", "traitement des e-mails", "chat en ligne", "upselling"]
LANGUES = ["Français", "Anglais", "Wolof", "Espagnol", "Arabe", "Portugais", "Pulaar", "Sérère"]
NIVEAUX_LANGUE = ["courant", "professionnel", "notions", "langue maternelle", "bilingue"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MISSIONS = ["Gestion des appels entrants et sortants", "Traitement des réclamations clients",
            "Suivi des dossiers dans le CRM", "Vente d'options et de services",
            "Relances téléphoniques des clients", "Réponse aux demandes par e-mail et chat",
            "Accueil et orientation de la clientèle", "Atteinte des objectifs de satisfaction",
            "Assistance technique de premier niveau", "Prise de rendez-vous commerciaux"]

TITRES = {
    "experience": ["EXPÉRIENCES PROFESSIONNELLES", "Expérience professionnelle", "PARCOURS PROFESSIONNEL",
                   "Expériences", "EXPÉRIENCE"],
    "formation": ["FORMATION", "Formation", "PARCOURS SCOLAIRE", "Éducation", "DIPLÔMES"],
    "competences": ["COMPÉTENCES", "Compétences", "SAVOIR-FAIRE", "Compétences clés"],
    "langues": ["LANGUES", "Langues", "Langues parlées"],
}


def couper(liste):
    """Sépare une liste en une partie entraînement et une partie test."""
    liste = liste[:]
    random.shuffle(liste)
    n = max(2, int(len(liste) * 0.3))
    return {"train": liste[n:], "test": liste[:n]}


POOLS = {nom: couper(valeurs) for nom, valeurs in {
    "prenom": PRENOMS, "nom": NOMS, "ville": VILLES, "entreprise": ENTREPRISES,
    "etablissement": ETABLISSEMENTS}.items()}


class Redacteur:
    """Écrit le texte du CV morceau par morceau en mémorisant la position
    exacte de chaque entité : les annotations sont donc toujours justes."""

    def __init__(self):
        self.texte = ""
        self.entites = []

    def ecrire(self, morceau):
        self.texte += morceau

    def entite(self, valeur, etiquette):
        debut = len(self.texte)
        self.texte += valeur
        self.entites.append((etiquette, debut, len(self.texte), valeur))


def une_date(r, annee):
    style = random.random()
    if style < 0.4:
        valeur = f"{random.choice(MOIS).capitalize()} {annee}"
    elif style < 0.6:
        valeur = f"{random.randint(1, 12):02d}/{annee}"
    else:
        valeur = str(annee)
    r.entite(valeur, "DATE")


def creer_cv(partie):
    pool = lambda nom: random.choice(POOLS[nom][partie])
    r = Redacteur()
    prenom, nom = pool("prenom"), pool("nom")
    nom_affiche = f"{prenom} {nom.upper() if random.random() < 0.5 else nom}"

    # --- En-tête -----------------------------------------------------
    r.entite(nom_affiche, "NOM")
    r.ecrire("\n")
    r.entite(random.choice(POSTES), "POSTE")
    r.ecrire("\n")
    separateur = random.choice([" | ", " - ", "\n"])
    r.entite(pool("ville"), "VILLE")
    if random.random() < 0.6:
        r.ecrire(", Sénégal")
    r.ecrire(separateur)
    r.ecrire(random.choice(["", "Tél. : ", "Tel : "]))
    numero = f"{random.choice(['77', '78', '76', '70', '75'])} {random.randint(100, 999)} " \
             f"{random.randint(10, 99)} {random.randint(10, 99)}"
    r.entite(random.choice(["+221 ", "", "(+221) "]) + numero, "TELEPHONE")
    r.ecrire(separateur)
    r.ecrire(random.choice(["", "E-mail : "]))
    domaine = random.choice(["example.com", "exemple.sn", "mail.example.org"])
    email = f"{prenom.lower()}.{nom.lower()}@{domaine}"
    email = email.replace("ï", "i").replace("è", "e").replace("é", "e")
    r.entite(email, "EMAIL")
    r.ecrire("\n\n")

    sections = ["experience", "formation", "competences", "langues"]
    if random.random() < 0.3:
        sections[0], sections[1] = sections[1], sections[0]
    annee = random.randint(2024, 2026)

    for section in sections:
        r.ecrire(random.choice(TITRES[section]) + "\n")
        if section == "experience":
            for _ in range(random.randint(1, 3)):
                fin, debut = annee, annee - random.randint(1, 3)
                annee = debut - random.randint(0, 1)
                if random.random() < 0.5:                      # « Poste - Entreprise, Ville » puis dates
                    r.entite(random.choice(POSTES), "POSTE")
                    r.ecrire(" - ")
                    r.entite(pool("entreprise"), "ENTREPRISE")
                    r.ecrire(", ")
                    r.entite(pool("ville"), "VILLE")
                    r.ecrire("\n")
                    une_date(r, debut)
                    r.ecrire(" - ")
                    if fin >= 2025 and random.random() < 0.5:
                        r.ecrire(random.choice(["Présent", "aujourd'hui"]))
                    else:
                        une_date(r, fin)
                    r.ecrire("\n")
                else:                                          # « dates : Poste, Entreprise »
                    une_date(r, debut)
                    r.ecrire(" - ")
                    une_date(r, fin)
                    r.ecrire(" : ")
                    r.entite(random.choice(POSTES), "POSTE")
                    r.ecrire(", ")
                    r.entite(pool("entreprise"), "ENTREPRISE")
                    r.ecrire("\n")
                for mission in random.sample(MISSIONS, random.randint(1, 3)):
                    r.ecrire(random.choice(["- ", "• ", ""]) + mission + "\n")
        elif section == "formation":
            for _ in range(random.randint(1, 2)):
                if random.random() < 0.5:
                    une_date(r, random.randint(2010, 2023))
                    r.ecrire(random.choice([" : ", "  "]))
                    r.entite(random.choice(DIPLOMES), "DIPLOME")
                    r.ecrire(" - ")
                    r.entite(pool("etablissement"), "ETABLISSEMENT")
                else:
                    r.entite(random.choice(DIPLOMES), "DIPLOME")
                    r.ecrire(", ")
                    r.entite(pool("etablissement"), "ETABLISSEMENT")
                    r.ecrire(" (")
                    une_date(r, random.randint(2010, 2023))
                    r.ecrire(")")
                r.ecrire("\n")
        elif section == "competences":
            choix = random.sample(COMPETENCES, random.randint(3, 6))
            sep = random.choice([", ", " ; ", "\n- "])
            if sep == "\n- ":
                r.ecrire("- ")
            for i, competence in enumerate(choix):
                if i:
                    r.ecrire(sep)
                r.entite(competence[0].upper() + competence[1:] if random.random() < 0.4 else competence,
                         "COMPETENCE")
            r.ecrire("\n")
        else:
            for i, langue in enumerate(random.sample(LANGUES, random.randint(2, 3))):
                if i:
                    r.ecrire(", ")
                r.entite(langue, "LANGUE")
                if random.random() < 0.5:
                    r.ecrire(f" ({random.choice(NIVEAUX_LANGUE)})")
            r.ecrire("\n")
        r.ecrire("\n")
    return r.texte.rstrip() + "\n", r.entites


def en_format_projet(texte, entites, partie):
    annotations = []
    for etiquette, debut, fin, valeur in entites:
        # Défaut volontaire n°1 : espace inclus dans l'entité (fréquent en annotation manuelle)
        if random.random() < 0.05 and fin < len(texte) and texte[fin] == " ":
            fin += 1
            valeur = texte[debut:fin]
        annotations.append({"label": [etiquette],
                            "points": [{"start": debut, "end": fin - 1, "text": valeur}]})
    # Défaut volontaire n°2 : une annotation en double qui chevauche une autre
    if random.random() < 0.1 and entites:
        etiquette, debut, fin, valeur = random.choice(entites)
        annotations.append({"label": ["COMPETENCE"],
                            "points": [{"start": debut, "end": fin - 1, "text": valeur}]})
    return {"content": texte, "annotation": annotations, "extras": {"partie": partie}}


os.makedirs("donnees", exist_ok=True)
compte = {"train": 0, "test": 0}
etiquettes = {}
with open(os.path.join("donnees", "cv_annotes.json"), "w", encoding="utf-8") as f:
    for i in range(NB_CV):
        partie = "test" if i < NB_CV * PART_TEST else "train"
        texte, entites = creer_cv(partie)
        f.write(json.dumps(en_format_projet(texte, entites, partie), ensure_ascii=False) + "\n")
        compte[partie] += 1
        for etiquette, *_ in entites:
            etiquettes[etiquette] = etiquettes.get(etiquette, 0) + 1

print(f"Fichier donnees/cv_annotes.json créé : {NB_CV} CV annotés "
      f"({compte['train']} entraînement, {compte['test']} test)")
print("Entités par étiquette :")
for etiquette, nombre in sorted(etiquettes.items(), key=lambda x: -x[1]):
    print(f"  {etiquette:<14} {nombre}")
