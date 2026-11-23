-- Contenu de la base
SELECT 'candidats' AS table_, COUNT(*) AS lignes FROM candidats
UNION ALL SELECT 'experiences', COUNT(*) FROM experiences
UNION ALL SELECT 'formations', COUNT(*) FROM formations
UNION ALL SELECT 'competences', COUNT(*) FROM competences
UNION ALL SELECT 'candidat_competences', COUNT(*) FROM candidat_competences
UNION ALL SELECT 'rejets', COUNT(*) FROM rejets
UNION ALL SELECT 'decisions', COUNT(*) FROM decisions;

-- Les 10 compétences métier les plus citées
SELECT k.libelle AS competence, COUNT(*) AS candidats
FROM candidat_competences cc
JOIN competences k ON k.id = cc.competence_id
WHERE k.type = 'metier'
GROUP BY k.id
ORDER BY candidats DESC, competence
LIMIT 10;

-- Expérience moyenne selon le niveau d'études
SELECT niveau_etudes AS bac_plus, COUNT(*) AS candidats,
       ROUND(AVG(annees_experience), 1) AS experience_moyenne_ans
FROM candidats
WHERE niveau_etudes IS NOT NULL
GROUP BY niveau_etudes
ORDER BY niveau_etudes;

-- Les 5 employeurs les plus fréquents
SELECT entreprise, COUNT(DISTINCT candidat_id) AS candidats,
       ROUND(AVG(duree_mois)) AS duree_moyenne_mois
FROM experiences
WHERE entreprise IS NOT NULL
GROUP BY entreprise
ORDER BY candidats DESC, entreprise
LIMIT 5;

-- Présélection par critères : 2 ans d'expérience, anglais, déjà en relation client
SELECT c.nom, c.source, c.annees_experience AS experience_ans,
       COUNT(*) OVER () AS total_candidats_trouves
FROM candidats c
WHERE c.annees_experience >= 2
  AND EXISTS (SELECT 1 FROM candidat_competences cc JOIN competences k ON k.id = cc.competence_id WHERE cc.candidat_id = c.id AND k.type = 'langue' AND k.cle = 'anglais')
  AND EXISTS (SELECT 1 FROM experiences e WHERE e.candidat_id = c.id
              AND e.categorie_poste IN ('Conseiller clientèle', 'Téléconseiller', 'Chargé de clientèle'))
ORDER BY c.annees_experience DESC
LIMIT 8;

-- Décisions passées : taux de candidats retenus selon l'anglais
SELECT CASE WHEN EXISTS (SELECT 1 FROM candidat_competences cc JOIN competences k ON k.id = cc.competence_id WHERE cc.candidat_id = c.id AND k.type = 'langue' AND k.cle = 'anglais') THEN 'parle anglais' ELSE 'sans anglais' END AS groupe,
       COUNT(*) AS candidats, ROUND(100.0 * AVG(d.retenu), 1) AS pourcentage_retenus
FROM candidats c
JOIN decisions d ON d.candidat_id = c.id
GROUP BY groupe;

-- Contrôle qualité : informations écartées ou corrigées à l'intégration
SELECT c.nom, r.champ, r.valeur, r.motif
FROM rejets r
JOIN candidats c ON c.id = r.candidat_id
ORDER BY c.id;

