# Banc de questions « naturelles » — Avaliance Copilot

Questions rédigées comme un consultant les taperait vraiment, en nommant
toujours le client et le programme. Chaque question est suivie de la réponse
attendue et de la page source dans le PDF.

Sept familles de questions : QUI (rôle) · COMMENT (déroulé) · COMBIEN (chiffre)
· POURQUOI (justification) · QUAND (date) · QUOI (techno / livrable) · PIÈGE
(réponse absente du corpus).

---

## 1. Helvia Assurances — programme SINAPS

1. **QUI** — Qui s'est occupé de la partie déploiement et cloud dans le projet Helvia Assurances (programme SINAPS) ?
   > Rémi Lasalle, ingénierie DevOps et cloud AWS (100 %, avril 2024 – juin 2025), assisté de Karim Benslimane sur le DevOps et l'observabilité (80 %). — p. 13

2. **QUI** — Qui était le sponsor du projet SINAPS chez Helvia Assurances ?
   > Marc Delaunay, directeur des systèmes d'information, à 10 % de charge. — p. 12

3. **QUI** — Qui a piloté la conduite du changement et la formation sur le projet Helvia Assurances ?
   > Fatou Sy (50 %, sept. 2024 – juin 2025), pour 112 jours et 78 400 € HT. — p. 13 et 14

4. **QUI** — Qui autorisait les mises en production dans le projet SINAPS ?
   > Matrice de responsabilités : le sponsor approuve, la direction de programme réalise, architecture et RSSI sont consultés. — p. 22

5. **COMMENT** — Comment s'est déroulée la bascule vers le nouveau système chez Helvia Assurances ?
   > Bascule progressive domaine par domaine derrière une façade de routage, avec journal de réconciliation, puis bascule complète et procès-verbal de vérification le 16/05/2025. — p. 22

6. **COMBIEN** — Combien de personnes ont travaillé sur le projet Helvia Assurances (SINAPS) ?
   > 20 personnes, dont 14 côté Avaliance et 6 côté Helvia, pour un effectif moyen de 14,2 ETP. — p. 13

7. **POURQUOI** — Pourquoi le jalon J2 a-t-il été retardé sur le projet SINAPS d'Helvia Assurances ?
   > Retard de 14 jours dû au raccordement réseau entre le site de Villeurbanne et AWS.

8. **COMBIEN** — Quels gains le projet SINAPS a-t-il apportés sur le délai de règlement des sinistres chez Helvia ?
   > Délai moyen ramené de 21 à 11,4 jours (−45,7 %) et 38 % des dossiers réglés sans intervention humaine.

9. **QUOI** — Quelles briques techniques ont été retenues pour la sécurité des secrets dans le projet Helvia Assurances ?
   > AWS KMS pour le chiffrement et AWS Secrets Manager pour les secrets applicatifs.

10. **PIÈGE** — Quel était le chiffre d'affaires annuel d'Helvia Assurances pendant le projet SINAPS ?
    > Information absente du corpus.

---

## 2. Novacom Télécom — programme HORIZON DATA

1. **QUI** — Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?
   > Pauline Vasseur, ingénierie data — flux temps réel (100 %, févr. – nov. 2025). — p. 13

2. **QUI** — Qui a développé le modèle d'attrition chez Novacom Télécom ?
   > Elsa Chaumette (science des données — modèle d'attrition), son industrialisation étant assurée par Raphaël Dombre. — p. 13

3. **QUI** — Qui s'est occupé de la reprise des bases héritées dans le projet Novacom Télécom ?
   > Diego Marchetti, ingénierie data — reprise des bases héritées (mars – août 2025). — p. 13

4. **QUI** — Qui était responsable de la qualité des données et de la conformité chez Novacom Télécom ?
   > Leila Bouzid (70 %, févr. – nov. 2025). — p. 13

5. **COMMENT** — Comment était organisée la gouvernance du programme HORIZON DATA chez Novacom Télécom ?
   > Comité de pilotage mensuel, comité data hebdomadaire réunissant les propriétaires de domaines, et revue de modèle mensuelle avec le marketing, le service client et la protection des données. — p. 13

6. **COMBIEN** — Quelle performance le modèle d'attrition a-t-il atteinte sur le projet Novacom Télécom ?
   > AUC passée de 0,71 à 0,86 avec LightGBM, pour une précision de 37 % sur les 5 % de clients les plus à risque.

7. **POURQUOI** — Pourquoi un avenant a-t-il été signé sur la mission Novacom Télécom ?
   > Avenant n° 1 du 02/09/2025, motivé par l'ajout du périmètre de résiliation fibre.

8. **QUOI** — Quel problème de qualité a été détecté sur le modèle d'attrition de Novacom Télécom ?
   > Une fuite d'information qui portait artificiellement l'AUC à 0,94, identifiée puis corrigée.

9. **COMBIEN** — Combien de pipelines de données ont été livrés dans le projet Novacom Télécom ?
   > 214 pipelines.

10. **PIÈGE** — Quelle est la part de marché de Novacom Télécom sur le segment grand public ?
    > Information absente du corpus.

---

## 3. TransAlpes Logistique — programme REMPART

1. **QUI** — Qui a réalisé la segmentation réseau dans le projet TransAlpes Logistique (programme REMPART) ?
   > Fabien Delcourt, ingénierie réseau et segmentation (100 %, mars – oct. 2025). — p. 12

2. **QUI** — Qui s'est occupé de la détection et des règles de supervision chez TransAlpes Logistique ?
   > Charlotte Vermeulen pour les règles de détection, Kevin Ambrosini pour l'analyse et les procédures de réponse. — p. 12

3. **QUI** — Qui a mené les tests d'intrusion sur le programme REMPART de TransAlpes Logistique ?
   > Samuel Ekang, tests d'intrusion et exercice adversaire (35 %, février puis novembre 2025). — p. 12

4. **COMMENT** — Comment le déploiement sur les sites s'est-il déroulé chez TransAlpes Logistique ?
   > Site par site pendant neuf mois, au rythme de quatre à six sites par mois, sur les fenêtres du dimanche après-midi, chaque site donnant lieu à une fiche de recette signée par le responsable d'agence. — p. 11 et 12

5. **QUI** — Qui présidait le comité de pilotage du programme REMPART chez TransAlpes Logistique ?
   > Le directeur général adjoint, Philippe Orsède, sponsor du programme. — p. 12

6. **COMBIEN** — Où en est TransAlpes Logistique sur la conformité NIS2 à l'issue du programme REMPART ?
   > 15 exigences sur 17 couvertes contre 3 au départ, 176 contrats sur 210 mis à jour et 51 équipements sur 62 traités.

7. **COMBIEN** — Quels gains de délai de détection le programme REMPART a-t-il apportés chez TransAlpes Logistique ?
   > MTTD ramené de 9 jours à 45 minutes et MTTR de 72 heures à 6 heures.

8. **POURQUOI** — Pourquoi l'investissement du programme REMPART est-il justifié chez TransAlpes Logistique ?
   > Une journée d'arrêt d'exploitation est estimée à 410 000 €, soit un retour sur investissement atteint dès environ 3,4 jours d'arrêt évités.

9. **QUOI** — Quel incident d'exploitation est survenu pendant le programme REMPART chez TransAlpes Logistique ?
   > Une interruption du WMS de 22 minutes lors d'une opération de segmentation.

10. **PIÈGE** — Quel outil de détection commerciale TransAlpes Logistique utilisait-il avant le programme REMPART ?
    > Information absente du corpus.

---

## 4. Volteris Énergies — programme FLUX

1. **QUI** — Qui a pris en charge la plateforme Kubernetes dans le projet Volteris Énergies (programme FLUX) ?
   > Gwenaëlle Perrot, ingénierie plateforme Kubernetes (100 %, sept. 2024 – déc. 2025), avec Tomas Vidal sur la fiabilité et Farid Belkacem sur le réseau et l'infrastructure comme code. — p. 11

2. **QUI** — Qui gérait la sécurité des objets connectés et les certificats chez Volteris Énergies ?
   > Diane Roussely (60 %, nov. 2024 – nov. 2025), pour 128 jours et 131 840 € HT. — p. 12 et 13

3. **QUI** — Qui était Tech Lead sur la collecte et le traitement des flux dans le projet Volteris Énergies ?
   > Nils Ehrhardt (320 jours, TJM 960 €, 307 200 € HT). — p. 11 et 13

4. **COMMENT** — Comment s'est déroulée la bascule du parc de compteurs chez Volteris Énergies ?
   > Migration en 34 lots de 25 000 à 60 000 compteurs, chaque lot faisant l'objet d'une autorisation formelle sur la base d'un rapport de rapprochement exigeant 99,95 % de concordance. — p. 12

5. **QUI** — Qui autorisait chaque lot de bascule dans le projet Volteris Énergies ?
   > La revue de migration bihebdomadaire, pilotée par la référente exploitation du parc Maïva Lanteri. — p. 12

6. **QUAND** — Quand l'astreinte d'exploitation a-t-elle été transférée aux équipes de Volteris Énergies ?
   > En novembre 2025. — p. 12

7. **QUOI** — Quel incident de production a touché la plateforme FLUX de Volteris Énergies ?
   > Un incident en juillet 2025 ayant nécessité un rejeu de 4 heures et provoqué 3 h 20 de retard sur la mise à disposition des mesures.

8. **COMBIEN** — Quels volumes la plateforme FLUX de Volteris Énergies traite-t-elle ?
   > 1,14 million de compteurs, 26,4 millions de mesures par jour, avec des pointes à 4 200 messages par seconde.

9. **COMBIEN** — Combien coûte l'exploitation de la plateforme FLUX chez Volteris Énergies ?
   > 26 900 € par mois d'infrastructure et de services, plus 2,3 ETP côté exploitation.

10. **PIÈGE** — Combien Volteris Énergies compte-t-il d'abonnés au tarif réglementé ?
    > Information absente du corpus.

---

## 5. Groupe Santélia — programme LIEN

1. **QUI** — Qui s'est occupé de la partie interopérabilité dans le projet Groupe Santélia (programme LIEN) ?
   > Nadir Cherkaoui, expert interopérabilité et référentiels de santé (90 %), le développement du socle étant assuré par Marion Estelle. — p. 12

2. **QUI** — Qui gérait l'hébergement de données de santé et le DevOps chez le Groupe Santélia ?
   > Ludivine Marcadet, ingénierie DevOps et hébergement de santé (80 %, avril 2025 – mars 2026). — p. 12

3. **QUI** — Qui a constitué le dossier d'homologation de sécurité du projet Groupe Santélia ?
   > Pascal Nguema, sécurité, conformité et dossier d'homologation (60 %, avril – déc. 2025) ; homologation prononcée le 14/10/2025 pour trois ans. — p. 12

4. **COMMENT** — Comment le déploiement des établissements s'est-il déroulé dans le projet Groupe Santélia ?
   > Site pilote de Rennes d'octobre à décembre 2025, puis généralisation aux six autres établissements de janvier à mars 2026, avec la formation de 1 900 personnes. — p. 11

5. **POURQUOI** — Pourquoi le parcours de préadmission a-t-il été modifié chez le Groupe Santélia ?
   > Le pilote a montré que la vérification d'identité provoquait 34 % d'abandons ; après simplification, ajout d'une aide téléphonique et réordonnancement des questions, le taux est retombé à 12 %. — p. 11

6. **QUI** — Qui était responsable de l'accessibilité du portail patient du Groupe Santélia ?
   > Gaël Prieur, développement frontend et accessibilité (100 %), pour un taux de conformité de 96 %. — p. 12

7. **COMMENT** — Comment les patients ont-ils été associés au projet LIEN du Groupe Santélia ?
   > Par un comité des usagers de six représentants, consulté quatre fois, dont les remarques ont conduit à reformuler neuf écrans et à autoriser la préadmission en plusieurs fois. — p. 12

8. **COMBIEN** — Quels résultats le portail patient du Groupe Santélia a-t-il produits sur les admissions ?
   > Préadmission en ligne passée de 0 à 61 %, temps d'admission réduit de 14 à 5 minutes, satisfaction de 4,3 sur 5.

9. **COMBIEN** — Combien coûte le maintien en condition opérationnelle du portail du Groupe Santélia ?
   > 268 000 € par an, le projet ayant par ailleurs bénéficié d'un financement externe de 412 000 €.

10. **PIÈGE** — Quel éditeur fournit le dossier patient informatisé du Groupe Santélia ?
    > Information absente du corpus.

---

## Comment fabriquer d'autres questions du même type

Gabarit : **[verbe interrogatif] + [objet précis] + « dans le projet [Client] (programme [NOM]) » + « ? »**

| Famille | Gabarit | Ce que ça teste |
|---|---|---|
| QUI | Qui s'est occupé de … dans le projet X ? | Extraction depuis un tableau d'équipe |
| COMMENT | Comment s'est déroulé … dans le projet X ? | Synthèse de plusieurs paragraphes |
| COMBIEN | Combien … dans le projet X ? | Précision numérique |
| POURQUOI | Pourquoi … sur le projet X ? | Raisonnement causal |
| QUAND | Quand … dans le projet X ? | Extraction de date |
| QUOI | Quelle technologie … dans le projet X ? | Vocabulaire technique |
| PIÈGE | Question dont la réponse n'existe pas | Refus d'inventer |

Règle d'or : une question = une seule information attendue. Les questions à
trois sous-questions font décrocher les petits modèles.
