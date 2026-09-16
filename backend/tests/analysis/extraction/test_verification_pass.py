# Tests para analysis/extraction/engine/verification_pass.py -- Fase 2
# (2026-09-14) de la auditoría RAG, arquitectura "dos pasadas" para riesgos:
# un llamado LLM aparte, tras el map-reduce, que audita los ítems ya
# extraídos contra las mismas reglas de la categoría (recortadas del propio
# prompt, nunca duplicadas a mano) y decide mantener/descartar/fusionar.

from __future__ import annotations

from analysis.extraction.engine import verification_pass


def _item(valor: str, citation: str = "cita") -> dict:
    return {
        "tipo": "economico",
        "subtipo": "comercial",
        "valor": valor,
        "extraction_status": "success",
        "source_references": [{"document_id": "doc-1", "citation": citation}],
    }


class TestApplyVerificationDecisions:
    def test_keep_discard_and_merge(self):
        items = [
            _item("uno", citation="cita uno"),
            _item("dos", citation="cita dos"),
            _item("tres", citation="cita tres"),
            _item("cuatro", citation="cita cuatro"),
        ]
        decisions = [
            {"id": 0, "action": "keep"},
            {"id": 1, "action": "discard", "reason": "no aplica"},
            {"id": 2, "action": "keep"},
            {"id": 3, "action": "merge_with", "target_id": 2},
        ]

        out = verification_pass._apply_verification_decisions(items, decisions)

        assert [item["valor"] for item in out] == ["uno", "tres cuatro"]
        assert len(out[1]["source_references"]) == 2

    def test_missing_decision_is_fail_open_kept(self):
        items = [_item("uno"), _item("dos")]
        decisions = [{"id": 0, "action": "discard"}]

        out = verification_pass._apply_verification_decisions(items, decisions)

        assert [item["valor"] for item in out] == ["dos"]

    def test_merge_with_target_not_kept_keeps_source_standalone(self):
        items = [_item("uno"), _item("dos")]
        decisions = [
            {"id": 0, "action": "discard"},
            {"id": 1, "action": "merge_with", "target_id": 0},
        ]

        out = verification_pass._apply_verification_decisions(items, decisions)

        # target (id 0) fue descartado -- el dato de id 1 no puede perderse.
        assert [item["valor"] for item in out] == ["dos"]

    def test_unknown_action_is_fail_open_kept(self):
        items = [_item("uno")]
        decisions = [{"id": 0, "action": "algo_no_reconocido"}]

        out = verification_pass._apply_verification_decisions(items, decisions)

        assert len(out) == 1

    def test_empty_decisions_keeps_everything(self):
        items = [_item("uno"), _item("dos"), _item("tres")]

        out = verification_pass._apply_verification_decisions(items, [])

        assert out == items

    def test_preserves_relative_order_of_survivors(self):
        items = [_item("a"), _item("b"), _item("c")]
        decisions = [
            {"id": 0, "action": "keep"},
            {"id": 1, "action": "discard"},
            {"id": 2, "action": "keep"},
        ]

        out = verification_pass._apply_verification_decisions(items, decisions)

        assert [item["valor"] for item in out] == ["a", "c"]


class TestBuildVerificationMessages:
    def test_rules_are_cut_before_chunks_placeholder(self):
        messages = verification_pass._build_verification_messages(
            prompt_file_name="riesgos.txt", root_key="riesgos", items=[_item("uno")]
        )

        roles = [role for role, _ in messages]
        assert roles == ["system", "human"]

        human = messages[1][1]
        assert "<contexto_pliego>" not in human
        assert "DIMENSIONES DE RIESGO PERMITIDAS" in human
        assert '"id": 0' in human
        assert "uno" in human

    def test_candidate_items_block_truncates_and_caps_citations(self):
        item = _item("valor largo")
        item["source_references"] = [
            {"citation": "x" * 500},
            {"citation": "cita dos"},
            {"citation": "cita tres, no deberia aparecer"},
        ]

        block = verification_pass._candidate_items_block([item])

        assert len(block) < 1000
        assert "cita tres" not in block
        assert "cita dos" in block


class TestRunVerificationPass:
    def test_empty_items_short_circuits_without_calling_llm(self, monkeypatch):
        called = {"n": 0}

        def fake_call_llm(*, messages, correlation_id):
            called["n"] += 1
            raise AssertionError("no debería llamarse con lista vacía")

        monkeypatch.setattr(verification_pass, "_call_llm", fake_call_llm)

        items, usage = verification_pass.run_verification_pass(
            [], prompt_file_name="riesgos.txt", root_key="riesgos", correlation_id="c1"
        )

        assert items == []
        assert called["n"] == 0
        assert usage["total_tokens"] == 0

    def test_applies_llm_decisions(self, monkeypatch):
        items = [_item("uno"), _item("dos")]

        def fake_call_llm(*, messages, correlation_id):
            return (
                {"decisions": [{"id": 0, "action": "keep"}, {"id": 1, "action": "discard"}]},
                {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            )

        monkeypatch.setattr(verification_pass, "_call_llm", fake_call_llm)

        out, usage = verification_pass.run_verification_pass(
            items, prompt_file_name="riesgos.txt", root_key="riesgos", correlation_id="c1"
        )

        assert [item["valor"] for item in out] == ["uno"]
        assert usage["total_tokens"] == 25

    def test_llm_failure_is_fail_open_returns_original_items(self, monkeypatch):
        items = [_item("uno"), _item("dos")]

        def fake_call_llm(*, messages, correlation_id):
            raise RuntimeError("azure caído")

        monkeypatch.setattr(verification_pass, "_call_llm", fake_call_llm)

        out, usage = verification_pass.run_verification_pass(
            items, prompt_file_name="riesgos.txt", root_key="riesgos", correlation_id="c1"
        )

        assert out == items
        assert usage["total_tokens"] == 0

    def test_malformed_response_is_fail_open_returns_original_items(self, monkeypatch):
        items = [_item("uno"), _item("dos")]

        def fake_call_llm(*, messages, correlation_id):
            return (
                {"algo_distinto": "sin decisions"},
                {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            )

        monkeypatch.setattr(verification_pass, "_call_llm", fake_call_llm)

        out, usage = verification_pass.run_verification_pass(
            items, prompt_file_name="riesgos.txt", root_key="riesgos", correlation_id="c1"
        )

        assert out == items
