from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

# 2026-09-10: la versión larga (~60 palabras, con "antecedentes técnicos",
# "plan de trabajo", "presentación técnica", "requisitos a cumplimentar"…)
# medía 0.917 de recall_production_effective; esta corta mide 0.979 (+0.062,
# 0 regresiones en otras categorías). El embedding de una query larga promedia
# y difumina el núcleo "anexo / formulario / planilla" -> vector más borroso.
# Solo afecta retrieval; el prompt de extracción (anexos_obligatorios.txt)
# sigue haciendo el trabajo fino.
_QUERY = "Formularios y anexos que deben completarse y presentarse con la oferta"


def extractor_anexos_obligatorios(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="anexos_obligatorios",
        state_field="anexos",
        status_field="anexos_status",
        prompt_file_name="anexos_obligatorios.txt",
        query=_QUERY,
    )
