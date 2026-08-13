from pathlib import Path
import unittest

from scripts.evaluate_rag import score_case, select_cases, summarize
from scripts.rag_golden import GoldenCase, load_golden_cases, score_positive_answer


ROOT = Path(__file__).resolve().parents[2]


class GoldenParserTests(unittest.TestCase):
    def test_loads_complete_specification(self) -> None:
        cases = load_golden_cases(ROOT / "Avaliance_Questions_Reponses_Claires.md")

        self.assertEqual(140, len(cases))
        self.assertEqual(20, len({case.project_id for case in cases}))
        self.assertEqual(120, sum(not case.should_abstain for case in cases))
        self.assertEqual(20, sum(case.should_abstain for case in cases))


class PositiveAnswerScoringTests(unittest.TestCase):
    def test_accepts_reordered_facts_with_exact_numbers(self) -> None:
        expected = (
            "Temps de mise en production passé de 6 semaines à 3 jours ; "
            "Disponibilité mesurée à 99,93 % sur trois mois."
        )
        actual = (
            "La disponibilité atteint 99,93 % sur trois mois et la mise en "
            "production passe de 6 semaines à 3 jours."
        )

        score = score_positive_answer(expected, actual)

        self.assertTrue(score["correct"])
        self.assertEqual([], score["missing_numbers"])

    def test_rejects_missing_numeric_fact(self) -> None:
        expected = "RTO validé à 42 minutes contre 6 heures auparavant."
        actual = "Le RTO a été fortement réduit et validé à 42 minutes."

        score = score_positive_answer(expected, actual)

        self.assertFalse(score["correct"])
        self.assertEqual(["6"], score["missing_numbers"])


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = GoldenCase(
            case_id="AVA-001-Q04",
            project_id="AVA-001",
            project_title="Projet",
            category="TECHNOLOGIES",
            question="Question",
            expected_answer="Java 21, React 18 et PostgreSQL.",
            expected_document="AVA-001.pdf",
            expected_page=4,
            should_abstain=False,
        )

    def test_source_and_page_must_match_same_expected_document(self) -> None:
        result = score_case(
            self.case,
            {
                "answer": "PostgreSQL, Java 21 et React 18.",
                "citations": [
                    {"documentName": "AVA-001.pdf", "page": 2},
                    {"documentName": "other.pdf", "page": 4},
                ],
            },
            1.0,
        )

        self.assertTrue(result["answer_correct"])
        self.assertTrue(result["source_correct"])
        self.assertFalse(result["page_correct"])

    def test_summary_keeps_metrics_separate(self) -> None:
        positive = score_case(
            self.case,
            {
                "answer": "PostgreSQL, Java 21 et React 18.",
                "citations": [{"documentName": "AVA-001.pdf", "page": 2}],
            },
            1.0,
        )
        abstention_case = GoldenCase(
            **{
                **self.case.to_dict(),
                "case_id": "AVA-001-Q07",
                "expected_answer": "Information insuffisante dans le corpus pour répondre de manière fiable.",
                "should_abstain": True,
            }
        )
        negative = score_case(
            abstention_case,
            {"answer": abstention_case.expected_answer, "citations": []},
            2.0,
        )

        summary = summarize([positive, negative])

        self.assertEqual(1.0, summary["positive_answer_accuracy"]["rate"])
        self.assertEqual(0.0, summary["expected_page_accuracy"]["rate"])
        self.assertEqual(1.0, summary["abstention_accuracy"]["rate"])

    def test_selects_one_question_for_every_second_document(self) -> None:
        cases = load_golden_cases(ROOT / "Avaliance_Questions_Reponses_Claires.md")

        selected = select_cases(cases, project_step=2, question_number=3)

        self.assertEqual(10, len(selected))
        self.assertEqual(
            [f"AVA-{number:03d}-Q03" for number in range(1, 21, 2)],
            [case.case_id for case in selected],
        )


if __name__ == "__main__":
    unittest.main()