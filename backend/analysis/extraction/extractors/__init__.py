from analysis.extraction.extractors.causales import extractor_causales
from analysis.extraction.extractors.criterios_evaluacion import extractor_criterios_evaluacion
from analysis.extraction.extractors.garantias import extractor_garantias
from analysis.extraction.extractors.identificacion_procedimiento import extractor_identificacion_procedimiento
from analysis.extraction.extractors.objeto_alcance import extractor_objeto_alcance
from analysis.extraction.extractors.plazos import extractor_plazos
from analysis.extraction.extractors.requisitos_admisibilidad import extractor_requisitos_admisibilidad
from analysis.extraction.extractors.anexos_obligatorios import extractor_anexos_obligatorios
from analysis.extraction.extractors.riesgos import extractor_riesgos

__all__ = [
    "extractor_plazos",
    "extractor_garantias",
    "extractor_causales",
    "extractor_objeto_alcance",
    "extractor_anexos_obligatorios",
    "extractor_requisitos_admisibilidad",
    "extractor_criterios_evaluacion",
    "extractor_identificacion_procedimiento",
    "extractor_riesgos",
]
