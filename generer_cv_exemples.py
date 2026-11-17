# ==============================================================
# Génère des CV FICTIFS de conseillers clientèle pour tester la phase 1
# (personnes, coordonnées et entreprises inventées)
#
# 4 formats différents, comme dans la réalité :
#   - cv_aminata_ndiaye.pdf   : PDF "numérique" (le texte est sélectionnable)
#   - cv_awa_sarr_scan.pdf    : PDF scanné (une simple image, il faut l'OCR)
#   - cv_moussa_fall_photo.png: photo d'un CV papier (légèrement penchée)
#   - cv_ibrahima_ba.docx     : document Word
# ==============================================================

import os
import random

import pdfplumber
from docx import Document
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DOSSIER = "cv_exemples"
os.makedirs(DOSSIER, exist_ok=True)
random.seed(42)

CV = {
    "aminata": [
        ("titre", "AMINATA NDIAYE"),
        ("sous", "Conseillère clientèle bilingue"),
        ("ligne", "Dakar, Sénégal  |  +221 77 512 34 56  |  aminata.ndiaye@example.com"),
        ("section", "PROFIL"),
        ("ligne", "Conseillère clientèle avec 6 ans d'expérience en centre de contact,"),
        ("ligne", "orientée satisfaction client et résolution au premier appel."),
        ("section", "EXPÉRIENCES PROFESSIONNELLES"),
        ("gras", "Conseillère clientèle - TéléServices Afrique, Dakar"),
        ("ligne", "Mars 2022 - Présent"),
        ("puce", "Gestion des appels entrants pour un opérateur télécom français"),
        ("puce", "Traitement des réclamations et suivi dans le CRM Salesforce"),
        ("puce", "Vente additionnelle d'options : 112 % de l'objectif en 2024"),
        ("gras", "Téléconseillère - Centre d'Appels Horizon, Dakar"),
        ("ligne", "Janvier 2020 - Février 2022"),
        ("puce", "Appels sortants de fidélisation et de recouvrement"),
        ("puce", "Réponse aux demandes clients par e-mail et chat"),
        ("section", "FORMATION"),
        ("ligne", "2019  Licence en Gestion des Entreprises - Université Cheikh Anta Diop"),
        ("ligne", "2016  Baccalauréat série L - Lycée Blaise Diagne, Dakar"),
        ("section", "COMPÉTENCES"),
        ("puce", "Relation client, écoute active, gestion des réclamations"),
        ("puce", "Vente additionnelle, fidélisation"),
        ("puce", "Salesforce, Zendesk, Pack Office"),
        ("section", "LANGUES"),
        ("ligne", "Français (courant), Anglais (professionnel), Wolof (langue maternelle)"),
        ("section", "CENTRES D'INTÉRÊT"),
        ("ligne", "Lecture, bénévolat associatif, basket-ball"),
    ],
    "awa": [
        ("titre", "Awa SARR"),
        ("sous", "Téléconseillère"),
        ("ligne", "Tél. : 78 645 12 90"),
        ("ligne", "E-mail : awa.sarr@example.com"),
        ("ligne", "Thiès, Sénégal"),
        ("section", "PARCOURS PROFESSIONNEL"),
        ("gras", "2023 - 2025 : Téléconseillère, Callmax Sénégal"),
        ("puce", "Service après-vente et assistance technique de niveau 1"),
        ("puce", "Respect des indicateurs : DMT, taux de résolution, satisfaction"),
        ("gras", "2022 - 2023 : Agent d'accueil (stage), Banque Atlantique Thiès"),
        ("puce", "Accueil et orientation de la clientèle"),
        ("section", "PARCOURS SCOLAIRE"),
        ("ligne", "2022 : BTS Communication d'entreprise, ISM Dakar"),
        ("ligne", "2020 : Baccalauréat série G"),
        ("section", "SAVOIR-FAIRE"),
        ("ligne", "Appels entrants ; assistance technique ; Excel ; Word ; prise de notes rapide"),
        ("section", "LANGUES"),
        ("ligne", "Français, Wolof, Anglais (notions)"),
    ],
    "moussa": [
        ("titre", "MOUSSA FALL"),
        ("sous", "Chargé de clientèle"),
        ("ligne", "Saint-Louis  -  70 321 54 87  -  moussa.fall@example.com"),
        ("section", "EXPÉRIENCE"),
        ("gras", "Chargé de clientèle, Orbis Télécom (2021 - 2024)"),
        ("puce", "Gestion d'un portefeuille de clients professionnels"),
        ("puce", "Négociation et vente de forfaits mobiles"),
        ("gras", "Commercial terrain, Distribution Plus (2019 - 2021)"),
        ("puce", "Prospection et vente en porte-à-porte"),
        ("section", "ÉDUCATION"),
        ("ligne", "Master 1 Marketing et Commerce - Université Gaston Berger (2019)"),
        ("section", "COMPÉTENCES"),
        ("ligne", "Négociation, prospection, CRM, Excel, communication"),
        ("section", "LANGUES"),
        ("ligne", "Français, Anglais, Pulaar"),
    ],
}


def creer_pdf(chemin, contenu):
    """Écrit un CV en PDF avec du vrai texte (sélectionnable)."""
    c = canvas.Canvas(chemin, pagesize=A4)
    largeur, hauteur = A4
    y = hauteur - 60
    for type_ligne, texte in contenu:
        if type_ligne == "titre":
            c.setFont("Helvetica-Bold", 22)
            c.drawString(50, y, texte)
            y -= 26
        elif type_ligne == "sous":
            c.setFont("Helvetica-Oblique", 14)
            c.drawString(50, y, texte)
            y -= 22
        elif type_ligne == "section":
            y -= 10
            c.setFont("Helvetica-Bold", 13)
            c.drawString(50, y, texte)
            c.line(50, y - 4, largeur - 50, y - 4)
            y -= 20
        elif type_ligne == "gras":
            c.setFont("Helvetica-Bold", 11)
            c.drawString(50, y, texte)
            y -= 15
        elif type_ligne == "puce":
            c.setFont("Helvetica", 11)
            c.drawString(60, y, "•  " + texte)
            y -= 15
        else:
            c.setFont("Helvetica", 11)
            c.drawString(50, y, texte)
            y -= 15
    c.save()


def pdf_en_image(chemin_pdf, resolution=200):
    """Transforme la première page d'un PDF en image (comme un scanner)."""
    with pdfplumber.open(chemin_pdf) as pdf:
        return pdf.pages[0].to_image(resolution=resolution).original.convert("RGB")


def abimer(image, angle):
    """Simule une photo / un scan : rotation, flou léger, grain."""
    image = image.rotate(angle, expand=True, fillcolor="white")
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    pixels = image.load()
    for _ in range(image.width * image.height // 400):      # quelques points parasites
        x, y = random.randrange(image.width), random.randrange(image.height)
        pixels[x, y] = (120, 120, 120)
    return image


# 1. PDF numérique
creer_pdf(os.path.join(DOSSIER, "cv_aminata_ndiaye.pdf"), CV["aminata"])

# 2. PDF scanné : le PDF ne contient qu'une image, aucun texte
temporaire = os.path.join(DOSSIER, "_temp.pdf")
creer_pdf(temporaire, CV["awa"])
scan = abimer(pdf_en_image(temporaire), angle=0.8)
scan.save(os.path.join(DOSSIER, "cv_awa_sarr_scan.pdf"), resolution=200)

# 3. Photo d'un CV papier (PNG)
creer_pdf(temporaire, CV["moussa"])
photo = abimer(pdf_en_image(temporaire), angle=-1.5)
photo.save(os.path.join(DOSSIER, "cv_moussa_fall_photo.png"))
os.remove(temporaire)

# 4. Document Word
doc = Document()
doc.add_heading("Ibrahima BA", level=0)
doc.add_paragraph("Agent de recouvrement / Conseiller clientèle")
doc.add_paragraph("Rufisque, Sénégal - +221 76 908 11 22 - ibrahima.ba@example.com")
doc.add_heading("Expériences professionnelles", level=1)
doc.add_paragraph("Septembre 2021 - aujourd'hui : Agent de recouvrement, Crédit Express Dakar")
doc.add_paragraph("Relances téléphoniques et négociation d'échéanciers", style="List Bullet")
doc.add_paragraph("Suivi des dossiers clients dans le logiciel de gestion", style="List Bullet")
doc.add_heading("Formation", level=1)
doc.add_paragraph("2021 : DUT Techniques de commercialisation - IUT de Dakar")
doc.add_heading("Compétences", level=1)
doc.add_paragraph("Recouvrement, négociation, gestion des appels sortants, Excel")
doc.add_heading("Langues", level=1)
doc.add_paragraph("Français, Wolof, Arabe")
doc.save(os.path.join(DOSSIER, "cv_ibrahima_ba.docx"))

print("CV fictifs créés dans le dossier", DOSSIER, ":")
for nom in sorted(os.listdir(DOSSIER)):
    print("  -", nom)
