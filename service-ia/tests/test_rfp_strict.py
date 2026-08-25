from app.schemas import RfpSection, RfpBullet, RfpBulletAnchor
from app.generation.rfp_quality import validate_section, truncate_to_budget

def test_cross_case_leakage():
    section = RfpSection(
        key="tech",
        title="Tech",
        body="Le client NOVASHIELD utilise une solution de fraude avec 54% de faux positifs.",
        bullets=[]
    )
    brief = "Une banque avec 90% de faux positifs et >800ms."
    warnings = validate_section(section, {"__brief__": brief})
    assert any("Valeur factuelle non sourcée" in w for w in warnings)
    
def test_cross_case_reference_is_allowed():
    section = RfpSection(
        key="tech",
        title="Tech",
        body="Par exemple, chez notre client Avaliance, le projet a réduit les délais de 54% [pdf-001].",
        bullets=[]
    )
    brief = "Une banque avec 90% de faux positifs et >800ms."
    class MockEvidence:
        quote = "Le projet a réduit les délais de 54%."
    warnings = validate_section(section, {"__brief__": brief, "pdf-001": MockEvidence()})
    # Shouldn't trigger cross-case leakage because of explicitly framed reference
    assert not any("cross-case leakage" in w for w in warnings)

def test_malformed_citation():
    section = RfpSection(
        key="tech",
        title="Tech",
        body="Ceci est un test [pdf. ou [1].",
        bullets=[]
    )
    warnings = validate_section(section, {"__brief__": "test"})
    assert any("malformée" in w for w in warnings)

def test_truncation_limits():
    section = RfpSection(
        key="tech",
        title="Tech",
        body="Test.",
        bullets=[
            RfpBullet(text="b1", anchor=RfpBulletAnchor(type="fact", id="1")),
            RfpBullet(text="b2", anchor=RfpBulletAnchor(type="fact", id="1")),
            RfpBullet(text="b3", anchor=RfpBulletAnchor(type="fact", id="1")),
            RfpBullet(text="b4", anchor=RfpBulletAnchor(type="fact", id="1")),
        ],
        assumptions=["a1", "a2", "a3"],
        questions=["q1", "q2", "q3", "q4"]
    )
    truncate_to_budget(section, 1000)
    assert len(section.bullets) == 3
    assert len(section.assumptions) == 2
    assert len(section.questions) == 3

