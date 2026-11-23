# ==============================================================
# Génère un jeu de CV FICTIFS annotés avec leurs ENTITÉS et leurs RELATIONS
# (la « vérité terrain » qui sert à valider la phase 4)
#
# Relations annotées (tête -> queue) :
#   A_OCCUPE   NOM -> POSTE            la personne a occupé ce poste
#   EMPLOYEUR  POSTE -> ENTREPRISE     le poste a été occupé dans cette entreprise
#   PERIODE    POSTE -> DATE           dates de début et de fin du poste
#   LIEU       ENTREPRISE -> VILLE     ville de l'entreprise
#   ECOLE      DIPLOME -> ETABLISSEMENT
#   OBTENU_EN  DIPLOME -> DATE
#
# Les CV mélangent deux styles d'écriture :
#   - en liste : « Poste - Entreprise, Ville » puis les dates sur la ligne suivante
#   - en phrases : « J'ai été Poste chez Entreprise à Ville de 2019 à 2021, puis… »
# Les noms, entreprises, villes et écoles sont ceux réservés au TEST en phase 3.
#
# Usage : python generer_donnees_relations.py
# ==============================================================

import json
import os
import random

from generer_donnees_annotees import (POOLS, POSTES, DIPLOMES, MOIS, MISSIONS,
                                      COMPETENCES, LANGUES, Redacteur)

random.seed(11)
NB_CV = 150


def pioche(nom):
    return random.choice(POOLS[nom]["test"])


def valeur_date(annee):
    style = random.random()
    if style < 0.4:
        return f"{random.choice(MOIS)} {annee}"
    if style < 0.6:
        return f"{random.randint(1, 12):02d}/{annee}"
    return str(annee)


def une_date(r, annee):
    return r.entite_index(valeur_date(annee), "DATE")


class RedacteurRelations(Redacteur):
    """Comme le Redacteur de la phase 3, mais garde aussi les relations."""

    def __init__(self):
        super().__init__()
        self.relations = []

    def entite_index(self, valeur, etiquette):
        self.entite(valeur, etiquette)
        return len(self.entites) - 1

    def relier(self, type_relation, tete, queue):
        self.relations.append((type_relation, tete, queue))


def experience_en_liste(r, nom, annee):
    """Conseillère clientèle - TéléServices Afrique, Dakar
       Mars 2022 - Décembre 2024"""
    fin, debut = annee, annee - random.randint(1, 3)
    poste = r.entite_index(random.choice(POSTES), "POSTE")
    r.ecrire(" - ")
    entreprise = r.entite_index(pioche("entreprise"), "ENTREPRISE")
    r.ecrire(", ")
    ville = r.entite_index(pioche("ville"), "VILLE")
    r.ecrire("\n")
    d1 = une_date(r, debut)
    r.ecrire(" - ")
    d2 = une_date(r, fin)
    r.ecrire("\n")
    for mission in random.sample(MISSIONS, random.randint(1, 2)):
        r.ecrire("- " + mission + "\n")
    for type_rel, tete, queue in (("A_OCCUPE", nom, poste), ("EMPLOYEUR", poste, entreprise),
                                  ("PERIODE", poste, d1), ("PERIODE", poste, d2),
                                  ("LIEU", entreprise, ville)):
        r.relier(type_rel, tete, queue)
    return debut - 1


def un_poste_en_phrase(r, nom, debut, fin, avec_ville):
    """Écrit « Poste chez Entreprise [à Ville] de D1 à D2 » et ses relations."""
    poste = r.entite_index(random.choice(POSTES).lower(), "POSTE")
    r.ecrire(" chez ")
    entreprise = r.entite_index(pioche("entreprise"), "ENTREPRISE")
    relations = [("A_OCCUPE", nom, poste), ("EMPLOYEUR", poste, entreprise)]
    if avec_ville:
        r.ecrire(" à ")
        ville = r.entite_index(pioche("ville"), "VILLE")
        relations.append(("LIEU", entreprise, ville))
    valeur = valeur_date(debut)
    r.ecrire(" d'" if valeur[0] in "aeiou" else " de ")     # « d'avril 2018 »
    d1 = r.entite_index(valeur, "DATE")
    r.ecrire(" à ")
    d2 = une_date(r, fin)
    relations += [("PERIODE", poste, d1), ("PERIODE", poste, d2)]
    for relation in relations:
        r.relier(*relation)


def experience_en_phrase(r, nom, annee):
    """Une phrase avec un ou deux postes : c'est là que la syntaxe compte."""
    fin2, debut2 = annee, annee - random.randint(1, 2)
    fin1, debut1 = debut2 - 1, debut2 - 1 - random.randint(1, 3)
    if random.random() < 0.6:
        r.ecrire(random.choice(["J'ai travaillé comme ", "J'ai été ", "Après une expérience de "]))
        un_poste_en_phrase(r, nom, debut1, fin1, random.random() < 0.7)
        r.ecrire(random.choice([", puis comme ", ", puis j'ai été ", ", avant de devenir "]))
        un_poste_en_phrase(r, nom, debut2, fin2, random.random() < 0.7)
        r.ecrire(".\n")
        return debut1 - 1
    r.ecrire(random.choice(["J'ai travaillé comme ", "J'ai occupé le poste de "]))
    un_poste_en_phrase(r, nom, debut2, fin2, random.random() < 0.7)
    r.ecrire(".\n")
    return debut2 - 1


def formation(r):
    diplome = r.entite_index(random.choice(DIPLOMES), "DIPLOME")
    if random.random() < 0.5:                  # « Licence ..., Université ... (2019) »
        r.ecrire(", ")
        ecole = r.entite_index(pioche("etablissement"), "ETABLISSEMENT")
        r.ecrire(" (")
        date = une_date(r, random.randint(2010, 2023))
        r.ecrire(")\n")
    else:                                      # « Licence ... obtenu en 2019 à Université ... »
        r.ecrire(random.choice([" obtenu en ", ", obtenu en "]))
        date = une_date(r, random.randint(2010, 2023))
        r.ecrire(random.choice([" à ", " auprès de "]))
        ecole = r.entite_index(pioche("etablissement"), "ETABLISSEMENT")
        r.ecrire("\n")
    r.relier("ECOLE", diplome, ecole)
    r.relier("OBTENU_EN", diplome, date)


def creer_cv():
    r = RedacteurRelations()
    prenom, nom_famille = pioche("prenom"), pioche("nom")
    nom = r.entite_index(f"{prenom} {nom_famille}", "NOM")
    r.ecrire("\n")
    r.entite(random.choice(POSTES), "POSTE")       # poste visé : pas une expérience
    r.ecrire("\n")
    r.entite(pioche("ville"), "VILLE")
    r.ecrire(" - ")
    r.entite(f"+221 {random.choice(['77', '78', '76'])} {random.randint(100, 999)} "
             f"{random.randint(10, 99)} {random.randint(10, 99)}", "TELEPHONE")
    r.ecrire(" - ")
    r.entite(f"{prenom.lower()}.{nom_famille.lower()}@example.com".replace("ï", "i")
             .replace("é", "e").replace("è", "e"), "EMAIL")
    r.ecrire("\n\nEXPÉRIENCES PROFESSIONNELLES\n")
    annee = random.randint(2024, 2026)
    for _ in range(random.randint(1, 3)):
        if random.random() < 0.5:
            annee = experience_en_liste(r, nom, annee)
        else:
            annee = experience_en_phrase(r, nom, annee)
    r.ecrire("\nFORMATION\n")
    for _ in range(random.randint(1, 2)):
        formation(r)
    r.ecrire("\nCOMPÉTENCES\n")
    for i, competence in enumerate(random.sample(COMPETENCES, 4)):
        r.ecrire(", " if i else "")
        r.entite(competence, "COMPETENCE")
    r.ecrire("\n\nLANGUES\n")
    for i, langue in enumerate(random.sample(LANGUES, 2)):
        r.ecrire(", " if i else "")
        r.entite(langue, "LANGUE")
    r.ecrire("\n")
    return r


def en_json(r):
    def point(i):
        _, debut, fin, valeur = r.entites[i]
        return {"start": debut, "end": fin, "text": valeur}
    return {
        "content": r.texte,
        "annotation": [{"label": [e], "points": [{"start": d, "end": f - 1, "text": v}]}
                       for e, d, f, v in r.entites],
        "relations": [{"type": t, "tete": point(a), "queue": point(b)} for t, a, b in r.relations],
        "extras": {"partie": "test"},
    }


def main():
    os.makedirs("donnees", exist_ok=True)
    compte = {}
    with open(os.path.join("donnees", "cv_relations.json"), "w", encoding="utf-8") as f:
        for _ in range(NB_CV):
            r = creer_cv()
            f.write(json.dumps(en_json(r), ensure_ascii=False) + "\n")
            for type_rel, *_ in r.relations:
                compte[type_rel] = compte.get(type_rel, 0) + 1
    print(f"Fichier donnees/cv_relations.json créé : {NB_CV} CV avec entités et relations")
    print("Relations par type :")
    for type_rel, nombre in sorted(compte.items(), key=lambda x: -x[1]):
        print(f"  {type_rel:<10} {nombre}")


if __name__ == "__main__":
    main()