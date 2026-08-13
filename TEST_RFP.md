# Tests d’acceptation RFP

Ce protocole couvre exclusivement `/api/rfp/generate`. Il ne modifie ni l’authentification, ni `/api/search`, ni l’ingestion documentaire, ni les données de production.

## Contrat attendu

- Les preuves internes sont exclusivement des extraits PDF avec `document`, `page physique`, `chunk` et extrait exact.
- Les missions sont des données synthétiques et sont toujours libellées **Mission synthétique** ; elles ne constituent pas une preuve.
- La réponse contient les 19 sections de proposition prévues.
- Chaque section distingue fait du brief, référence interne vérifiée, recommandation et hypothèse.
- Les tableaux sont structurés dans le JSON puis rendus par des éléments HTML `<table>`, jamais par un tableau Markdown brut.
- En l’absence de preuve PDF pertinente, l’API renvoie `NO_RELEVANT_PDF_EVIDENCE`, sans présenter de référence comme un fait vérifié.

## Cas représentatifs

| Cas | Brief | Vérifications |
|---|---|---|
| Santé / HDS | Portail patient, reprise d’historique, API, HDS, IAM/INS, accessibilité, formation et échéance de financement | Extraction HDS/portail/API ; aucune mission bancaire non comparable ; pages/chunks visibles pour les preuves PDF. |
| Télécom / données | Plateforme de données, interfaces et qualité de service | Extraits PDF adaptés ; architecture, intégrations, tests et indicateurs structurés. |
| Logistique / cybersécurité | Modernisation d’échanges, exigences de sécurité et déploiement | Risques, dépendances, conformité et plan de déploiement exprimés comme recommandations/hypothèses lorsque non établis. |
| Énergie / IoT | Collecte IoT, supervision et volumes | Indicateurs et contraintes de volumétrie ne sont affirmés que s’ils sont cités. |
| Assurance / cloud | Modernisation cloud et migration progressive | Stratégie de migration, recette et exploitation structurées. |
| Sans référence | Besoin volontairement hors corpus | `evidenceValidationPassed=false`, diagnostic `NO_RELEVANT_PDF_EVIDENCE`, aucune fausse référence. |

## Vérifications navigateur

1. Soumettre chaque brief sur `/propositions`.
2. Vérifier les 19 titres, les badges de nature des informations et au moins un vrai tableau HTML quand applicable.
3. Vérifier que chaque carte PDF affiche document, page physique, chunk et extrait.
4. Vérifier qu’une mission synthétique est explicitement libellée et que le message « Aucune mission suffisamment comparable » apparaît si nécessaire.
5. Vérifier copie et téléchargement lisibles, sans syntaxe de tableau Markdown dans la page.
6. Rejouer un smoke test de connexion, recherche et document après un déploiement RFP.

## Limites actuelles

La comparabilité synthétique ne doit jamais être confondue avec une référence PDF. Les décisions d’architecture, coûts, délais et engagements non fournis dans le brief restent des recommandations ou des hypothèses à valider.
