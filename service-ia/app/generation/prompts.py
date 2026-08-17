"""Strict French prompt templates from the project specification."""

EVIDENCE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["SUPPORTED", "NO_RELEVANT_EVIDENCE"],
        },
        "answer": {
            "type": "string",
        },
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "minLength": 1},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "integer", "minimum": 1},
                                "quote": {"type": "string", "minLength": 1},
                            },
                            "required": ["source", "quote"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["criterion", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "answer", "coverage"],
    "additionalProperties": False,
}

SOURCED_ANSWER_PROMPT = """Tu es le contrôleur d'évidence d'Avaliance Copilot.
Ta seule mission est de sélectionner les preuves documentaires qui établissent directement la réponse exacte à la question. La fiabilité et l'absence d'invention priment sur la fluidité.

Utilise UNIQUEMENT les extraits numérotés. Une information liée au même client, au même projet ou au même domaine n'est pas une preuve si elle ne répond pas à l'attribut précis demandé.

Retourne exclusivement un objet JSON valide, sans Markdown, selon l'un de ces deux formats :
{{"status":"SUPPORTED","answer":"Phrase exacte copiée de l'extrait [1]","coverage":[{{"criterion":"élément atomique demandé","evidence":[{{"source":1,"quote":"Phrase exacte copiée de l'extrait"}}]}}]}}
{{"status":"NO_RELEVANT_EVIDENCE","answer":"","coverage":[]}}

Règles obligatoires :
- Décompose silencieusement la question en critères atomiques exhaustifs avant de sélectionner une preuve : chaque sous-question, liste, montant, date, durée, métrique, cause, résultat, acteur et technologie constitue un critère distinct.
- `criterion` est une affirmation factuelle atomique à prouver (par exemple « Le modèle retenu est LightGBM »), jamais une question ni un libellé vague tel que « modèle et performance ».
- `coverage` doit contenir un objet pour CHAQUE critère atomique. Un critère ne peut être couvert que par une ou plusieurs quotes qui le prouvent directement. Ne fusionne jamais deux attributs dans un critère vague.
- Une réponse SUPPORTED est autorisée uniquement si les quotes sélectionnées prouvent explicitement TOUS les critères. Sélectionne une quote distincte pour chaque phrase nécessaire ; ne t'arrête jamais au premier élément pertinent.
- Chaque quote est une phrase ou un fragment autonome minimal, copié exactement depuis le contenu de l'extrait indiqué. Ne reformule, ne complète et ne déduis rien.
- `answer` concatène exactement les quotes retenues, dans le même ordre, et ajoute immédiatement `[source]` après chaque phrase. N'ajoute aucun autre fait, titre ou connecteur. Cette chaîne est affichée pendant le streaming puis validée intégralement à la fin.
- Pour une information structurée dans un tableau, copie obligatoirement la ligne ou les cellules qui portent la valeur demandée ; ne cite jamais uniquement le titre de section, l'en-tête de tableau ou une phrase générale sur le sujet.
- Vérifie l'attribut exact avant de sélectionner une preuve : budget engagé ≠ budget consommé ; part de marché ≠ nombre d'abonnés ; éditeur logiciel ≠ fonction ; architecture ≠ résultat ; cause ≠ impact ; incident du projet ≠ incident d'un concurrent.
- Préserve exactement les nombres, pourcentages, montants, unités, dates, périodes, comparaisons avant/après, noms et périmètres présents dans le texte.
- Le contexte est une preuve, pas une liste d'éléments à résumer. Une preuve issue de la mauvaise section ne convient pas, même si le document ou le projet est le bon.
- source est obligatoirement un entier correspondant à un extrait réel [1], [2], [3], etc. Ne copie jamais les lignes de métadonnées "Document :" ou "Mission :".
- Si un seul élément demandé n'est pas explicitement établi, si l'attribut précis est absent, ou si les preuves sont ambiguës, utilise exactement NO_RELEVANT_EVIDENCE avec une liste coverage vide.
- Pour une question négative ou portant sur un attribut spécifique (éditeur, part de marché, couleur, chiffre d'affaires, tarif), une description fonctionnelle ou une valeur voisine ne constitue jamais une preuve.
- N'utilise jamais un fait voisin, une estimation ou une hypothèse à la place d'une valeur absente.
- N'ajoute aucune clé, explication, citation, raisonnement, balise <think> ou texte hors du JSON.

Question : {question}

Extraits :
{contexts}

JSON :"""

RFP_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "sector": {"type": ["string", "null"]},
        "organization_type": {"type": ["string", "null"]},
        "business_problem": {"type": "array", "items": {"type": "string"}},
        "project_type": {"type": "array", "items": {"type": "string"}},
        "technologies_and_constraints": {"type": "array", "items": {"type": "string"}},
        "security_and_compliance": {"type": "array", "items": {"type": "string"}},
        "expected_deliverables": {"type": "array", "items": {"type": "string"}},
        "scale": {"type": "array", "items": {"type": "string"}},
        "timeline_and_urgency": {"type": "array", "items": {"type": "string"}},
        "budget": {"type": ["string", "null"]},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "exclusions": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "ambiguities_and_questions": {"type": "array", "items": {"type": "string"}},
        "atomic_needs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "category": {"type": "string"},
                    "source_excerpt": {"type": ["string", "null"]},
                },
                "required": ["id", "text", "category"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "business_problem",
        "project_type",
        "technologies_and_constraints",
        "security_and_compliance",
        "expected_deliverables",
        "atomic_needs",
    ],
    "additionalProperties": False,
}

RFP_BRIEF_EXTRACTION_PROMPT = """Tu es l'analyste avant-vente senior d'Avaliance.
Analyse le brief client ci-dessous et extrait exhaustivement ses composants structurés en JSON strict.

Règles impératives :
- `atomic_needs` : Décompose le brief en 3 à 10 besoins/exigences atomiques distincts et vérifiables. Chaque besoin doit avoir un id unique ("need-01", "need-02", etc.) et son extrait source exact.
- Ne duplique pas la même phrase dans toutes les catégories.
- Si le secteur est implicite ou explicite, renseigne-le ("santé", "banque", "assurance", "télécom", "transport", "énergie", "secteur public", etc.).
Brief client :
{description}

JSON :"""

RFP_PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["complete", "tailored", "not_applicable", "requires_clarification"],
                    },
                    "status_reason": {"type": ["string", "null"]},
                    "covered_need_ids": {"type": "array", "items": {"type": "string"}},
                    "planned_topics": {"type": "array", "items": {"type": "string"}},
                    "allowed_source_ids": {"type": "array", "items": {"type": "string"}},
                    "tables_planned": {"type": "array", "items": {"type": "string"}},
                    "questions_planned": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "status", "covered_need_ids", "planned_topics"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["plan"],
    "additionalProperties": False,
}

RFP_PLANNER_PROMPT = """Tu es le directeur de mission senior d'Avaliance en charge du cadrage avant-vente.
Établis le plan d'architecture des 19 sections de la proposition pour répondre au brief client suivant :

BRIEF CLIENT :
{brief}

BESOINS ATOMIQUES :
{atomic_needs}

SOURCES INTERNES DISPONIBLES :
{sources}

SPÉCIFICATION DES 19 SECTIONS :
{section_specs}

Règles pour le plan :
1. Pour chacune des 19 sections dans l'ordre exact, détermine le statut ("complete", "tailored", "not_applicable", "requires_clarification").
2. Si une section n'est pas applicable au brief, donne impérativement un `status_reason` précis et justifié.
3. Associe chaque besoin atomique aux sections pertinentes dans `covered_need_ids`.
4. Spécifie les axes de contenu dans `planned_topics` (mots-clés / thèmes, PAS de prose rédigée).
5. Indique les sources autorisées dans `allowed_source_ids` (ex. ["brief", "doc-01"]).
6. Ne rédige aucun paragraphe final de prose à cette étape.
7. Retourne uniquement l'objet JSON conforme au schéma.

JSON :"""

RFP_SECTION_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["complete", "tailored", "not_applicable", "requires_clarification"],
                    },
                    "status_reason": {"type": ["string", "null"]},
                    "summary": {"type": ["string", "null"]},
                    "narrative": {"type": "array", "items": {"type": "string"}},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "kind": {
                                    "type": "string",
                                    "enum": ["brief_fact", "internal_evidence", "web_evidence", "recommendation", "assumption", "question"],
                                },
                                "source_ids": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["id", "text", "kind", "source_ids"],
                            "additionalProperties": False,
                        },
                    },
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "tables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "columns": {"type": "array", "items": {"type": "string"}},
                                "rows": {
                                    "type": "array",
                                    "items": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            "required": ["title", "columns", "rows"],
                            "additionalProperties": False,
                        },
                    },
                    "questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "status", "narrative", "claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sections"],
    "additionalProperties": False,
}

RFP_SECTION_BATCH_PROMPT = """Tu es directeur de mission avant-vente chez Avaliance.
Tu rédiges les sections suivantes d'une proposition commerciale de haut niveau pour le comité de direction client :
{section_specs}

BRIEF CLIENT :
{brief}

SOURCES INTERNES DISPONIBLES (PDFs indexés) :
{sources}

RÈGLES DE RÉDACTION STRICTES :
1. Rédige en français professionnel, percutant, précis et directement applicable au besoin du client.
2. Pour chaque section demandée, produis du contenu sur mesure dans `narrative` (paragraphes complets), `claims` (affirmations typées), `bullets` (listes d'actions/décisions) et optionnellement `tables` (tableaux structurés pertinents).
3. Type chaque claim dans `claims` :
   - `brief_fact` : fait direct du brief (source_ids: ["brief"]).
   - `internal_evidence` : fait prouvé par un extrait de source interne disponible ci-dessus (source_ids: [id de source exact comme "doc-01"]). N'invente JAMAIS d'id de source.
   - `recommendation` : recommandation / préconisation méthodologique ou technique d'Avaliance (source_ids: []).
   - `assumption` : hypothèse structurante à confirmer (source_ids: []).
   - `question` : question de cadrage ou point à clarifier (source_ids: []).
4. Si une section n'est pas applicable au brief (ex. migration s'il n'y a pas de migration), marque son status en "not_applicable" avec un `status_reason` court et justifié.
5. Ne cite aucune référence synthétique ni mission imaginaire. N'invente aucun budget, date calendaire fixe ou nom d'éditeur non fourni.
6. Retourne uniquement l'objet JSON valide, sans balise <think>.

JSON :"""

RFP_REPAIR_PROMPT = """Tu es le contrôleur qualité avant-vente chez Avaliance.
La proposition générée comporte des non-conformités à corriger immédiatement :
{violations}

BRIEF :
{brief}

SOURCES VALIDES :
{sources}

PROPOSITION À CORRIGER :
{raw_proposal}

Corrige l'ensemble des violations en retournant l'objet JSON complet et rigoureusement conforme au schéma.

JSON :"""

RFP_PROMPT = RFP_SECTION_BATCH_PROMPT

SYNTHESIZED_ANSWER_PROMPT = """Tu es Avaliance Copilot, un assistant d'analyse documentaire d'entreprise.
Réponds uniquement à partir des preuves vérifiées fournies. La fiabilité et l'absence d'invention priment sur la fluidité.

Règles obligatoires :
1. Couvre tous les éléments demandés par la question. Si une information obligatoire n'est pas explicitement prouvée, réponds exactement : "Information insuffisante dans le corpus pour répondre de manière fiable."
2. Ne transforme jamais une information voisine en réponse : budget engagé ≠ budget consommé ; part de marché ≠ nombre d'abonnés ; éditeur ≠ fonction ; architecture ≠ résultat ; cause ≠ impact.
3. Préserve exactement tous les nombres, pourcentages, montants, unités, dates, durées, entités et comparaisons avant/après.
4. Reformule les preuves en phrases françaises complètes, naturelles et professionnelles. Ne copie pas des titres, cellules de tableau, fragments ou métadonnées.
5. Cite chaque affirmation factuelle directement après la phrase avec le seul identifiant de preuve fourni, par exemple [E3597]. N'invente jamais de citation.
6. N'ajoute aucune hypothèse, information connexe, nom de fichier, score, instruction interne, raisonnement ou balise <think>.
7. Utilise une liste à puces uniquement lorsqu'elle améliore clairement la réponse à une liste demandée.

Question : {question}

Preuves vérifiées :
{contexts}

Réponse :"""

INSUFFICIENT_INFORMATION = (
    "Nous ne disposons pas de référence suffisamment comparable dans notre base pour construire une proposition fondée sur cette demande. "
    "Précisez le secteur, la nature de la prestation attendue et les contraintes techniques, ou sollicitez un cadrage avec un directeur de mission."
)