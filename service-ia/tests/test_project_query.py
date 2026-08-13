from app.project_query import project_reference_from_query, project_title_from_query


def test_project_title_supports_suffix_position_unquoted_query():
    query = "Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?"
    assert project_title_from_query(query) == "Novacom Télécom (programme HORIZON DATA)"


def test_project_title_supports_le_projet_prefix_with_question_clause():
    query = "Le projet Volteris Énergies, quelles technologies ont été retenues pour l’architecture cible ?"
    assert project_title_from_query(query) == "Volteris Énergies"


def test_project_title_supports_du_projet_prefix():
    query = "Quelle difficulté principale du projet TransAlpes Logistique a été rencontrée ?"
    assert project_title_from_query(query) == "TransAlpes Logistique"


def test_project_title_supports_quoted_names_with_punctuation():
    query = "Dans le projet « Santelia-360 v2 », que faut-il retenir ?"
    assert project_title_from_query(query) == "Santelia-360 v2"


def test_project_title_returns_none_for_generic_project_wording():
    query = "Dans le projet, quelle difficulté a été rencontrée ?"
    assert project_title_from_query(query) is None


def test_project_reference_normalizes_embedded_reference():
    query = "Comment l'équipe du projet ava 012 a-t-elle évité le risque ?"
    assert project_reference_from_query(query) == "AVA-012"
