from types import SimpleNamespace

from app.generation.rfp_proposal import (
    STANDARD_SECTIONS_B,
    STANDARD_SECTIONS_C,
    _grounded_fallback_sections,
)


SPECS = STANDARD_SECTIONS_B + STANDARD_SECTIONS_C


def build(description: str):
    needs = [
        SimpleNamespace(id=str(index), text=part)
        for index, part in enumerate(description.split(". "), start=1)
        if part.strip()
    ]
    return _grounded_fallback_sections(needs, SPECS, [], description)


def visible(sections):
    values = []
    for section in sections:
        values.append(section.body)
        values.extend(bullet.text for bullet in section.bullets)
    return " ".join(values).lower()


def test_fallback_is_specific_to_streaming_payments_brief():
    description = (
        "Une institution financière veut migrer une architecture batch vers une plateforme temps réel Apache Kafka et Java. "
        "L'objectif est de traiter 15 000 événements par seconde avec une latence p95 inférieure à 200 ms pour des transactions de paiement instantanées."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    assert "kafka" in text and "java" in text
    assert "15 000" in text and "200 ms" in text
    assert "prototype" in text and "tests de charge" in text
    assert "90%" not in text and "lcb-ft" not in text


def test_fallback_is_specific_to_health_brief_and_does_not_leak_payments():
    description = (
        "Un réseau hospitalier souhaite centraliser les rendez-vous et réduire de 30% les absences. "
        "La solution doit intégrer une API FHIR, respecter les exigences RGPD et fournir un tableau de bord pour les équipes soignantes."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    assert "30%" in text and "fhir" in text and "rgpd" in text
    assert "règles" in text or "sécurité" in text
    assert "15 000" not in text and "200 ms" not in text
    assert "kafka" not in text and "java" not in text


def test_fallback_has_named_deliverables_and_no_reference_case_names():
    description = (
        "Une banque veut réduire 90% de faux positifs et une latence supérieure à 800ms dans la détection de fraude LCB-FT. "
        "Elle demande Kafka, des règles métiers versionnées et des modèles explicables."
    )
    sections = build(description)
    text = visible(sections)
    delivery = next(section for section in sections if section.key == "delivery_and_deliverables")
    assert "note d’architecture" in delivery.body
    assert "matrice de critères" in delivery.body
    assert "prototype validé" in delivery.body
    assert "plan de mise en service" in delivery.body
    assert "crédalis" not in text and "novashield" not in text
    assert "15 000" not in text and "200 ms" not in text


def test_fallback_preserves_compliance_and_retention_requirements():
    description = (
        "Dans le cadre de la digitalisation de son parcours d'ouverture de compte, un établissement financier cherche à automatiser "
        "la vérification des pièces d'identité et le contrôle LCB-FT au fil de l'eau. "
        "Le projet nécessite l'intégration d'API REST temps réel, le respect du RGPD, ainsi qu'un archivage probant des preuves de décision pendant 10 ans."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    for required in ("pièces d’identité", "lcb-ft", "api rest", "rgpd", "archivage", "10 ans"):
        assert required in text, required
    assert "rgpd, api" not in text
    assert "technologies concernées sont : rgpd" not in text
    assert "crédalis" not in text and "novashield" not in text


def test_fallback_preserves_insurance_business_requirements():
    description = (
        "Une compagnie d’assurance souhaite accélérer la gestion des sinistres automobiles. "
        "Elle veut permettre aux clients de déclarer un sinistre depuis une application mobile, de joindre des photographies et des documents, puis de suivre l’avancement de leur dossier en temps réel. "
        "La solution doit intégrer les systèmes existants de gestion des contrats, respecter le RGPD et conserver l’historique des décisions et des échanges pour une durée de sept ans. "
        "Le client souhaite réduire les délais de traitement et améliorer la traçabilité des décisions."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    for required in ("sinistres", "application mobile", "photographies", "documents", "temps réel", "systèmes existants", "7 ans", "délais de traitement"):
        assert required in text, required
    solution = next(section for section in sections if section.key == "proposed_solution")
    assert "application mobile" in solution.body
    assert "photographies" in solution.body
    assert "temps réel" in solution.body
    assert "systèmes existants" in solution.body


def test_fallback_preserves_iot_maintenance_requirements():
    description = (
        "Un groupe industriel souhaite mettre en place une solution de maintenance prédictive pour ses équipements de production. "
        "Des capteurs IoT transmettront les données de température, vibration et consommation énergétique vers une plateforme centralisée. "
        "La solution devra détecter les anomalies, prioriser les alertes et permettre aux équipes de maintenance de planifier les interventions avant une panne. "
        "Le système doit fonctionner avec les équipements existants, fournir un tableau de bord opérationnel et garantir la traçabilité des alertes et des actions réalisées."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    for required in ("maintenance prédictive", "capteurs iot", "température", "vibration", "anomalies", "alertes", "tableau de bord"):
        assert required in text, required
    assert "kafka" not in text and "lcb-ft" not in text


def test_fallback_preserves_public_service_requirements():
    description = (
        "Une administration souhaite digitaliser le traitement des demandes de documents officiels. "
        "Les citoyens doivent pouvoir déposer leur demande en ligne, transmettre les pièces justificatives et suivre son statut. "
        "La solution devra vérifier la complétude des dossiers, orienter les demandes vers les services compétents et conserver une piste d’audit de toutes les décisions. "
        "Elle doit respecter les exigences de protection des données, intégrer les systèmes administratifs existants et permettre l’archivage des dossiers conformément aux règles de conservation applicables."
    )
    sections = build(description)
    text = visible(sections)
    assert len(sections) == 6
    for required in ("administration", "en ligne", "pièces justificatives", "statut", "complétude", "piste d’audit", "archivage"):
        assert required in text, required
    assert "kafka" not in text and "java" not in text and "lcb-ft" not in text
