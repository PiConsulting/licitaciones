"""
Validaciones para Timeline.

Este módulo implementa validaciones defensivas para asegurar que los
deadlines tengan todos los campos necesarios antes de intentar calcular fechas.
"""
import logging
from typing import Optional

from pydantic import BaseModel

from timeline.models import Deadline
from timeline.service import TimelineService

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """
    Resultado de una validación.
    
    Attributes:
        is_valid: True si la validación pasó sin errores
        errors: Lista de mensajes de error (vacía si is_valid=True)
        warnings: Lista de advertencias que no impiden el cálculo
    """
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class RecalculationResult(BaseModel):
    """
    Resultado de un recálculo de fechas en cascada.
    
    PATCH: Modelo tipado para reemplazar dict genérico.
    
    Attributes:
        events_updated: Número de eventos actualizados
        errors: Lista de mensajes de error encontrados
    """
    events_updated: int
    errors: list[str] = []


def validate_deadline_for_calculation(
    service: TimelineService,
    analysis_id: str,
    deadline: Deadline,
    user_id: Optional[str] = None
) -> ValidationResult:
    """
    Valida que un deadline tiene todos los campos necesarios para calcular.
    
    Esta función realiza validaciones defensivas antes de intentar calcular
    una fecha para un deadline. Verifica:
    - Que el evento trigger exista y tenga fecha asignada
    - Que el evento target exista
    - Que la duración sea válida (> 0)
    - Que la unidad sea soportada ("días", "horas", "meses" o "años")
    - Que el day_type sea conocido ("corridos" o "hábiles")
    
    Args:
        service: Instancia de TimelineService para acceso a eventos
        analysis_id: ID del análisis
        deadline: Deadline a validar
        user_id: ID del usuario (opcional para tests con mocks)
    
    Returns:
        ValidationResult con:
            - is_valid: True si pasó todas las validaciones
            - errors: Lista de errores encontrados
            - warnings: Lista de advertencias no críticas
    
    Examples:
        >>> service = TimelineService(db)
        >>> result = validate_deadline_for_calculation(service, "analysis-1", deadline)
        >>> if not result.is_valid:
        ...     print(result.errors)
    """
    errors = []
    warnings = []
    
    logger.debug(f"Validando deadline {deadline.deadline_id} para cálculo")
    
    # 1. Validar que trigger_event existe y tiene fecha (AC1)
    trigger_event = service.get_event(deadline.trigger_event_id, analysis_id, user_id)
    
    if not trigger_event:
        error_msg = (
            f"Evento disparador '{deadline.trigger_event_id}' no existe en el análisis"
        )
        errors.append(error_msg)
        logger.warning(error_msg)
    elif not trigger_event.event_date:
        error_msg = (
            f"Evento disparador '{trigger_event.name}' no tiene fecha asignada. "
            "Se requiere una fecha para calcular el deadline."
        )
        errors.append(error_msg)
        logger.warning(error_msg)
    
    # 2. Validar que target_event existe (AC1)
    target_event = service.get_event(deadline.target_event_id, analysis_id, user_id)
    
    if not target_event:
        error_msg = (
            f"Evento resultado '{deadline.target_event_id}' no existe en el análisis"
        )
        errors.append(error_msg)
        logger.warning(error_msg)
    
    # 3. Validar duración (AC1)
    if deadline.duration <= 0:
        error_msg = (
            f"Duración debe ser positiva, recibido: {deadline.duration}. "
            "No se puede calcular con duración cero o negativa."
        )
        errors.append(error_msg)
        logger.error(error_msg)
    
    # 4. Validar unidad (AC1). "días" sigue siendo la más común, pero
    # "horas", "meses" y "años" también son unidades válidas del schema de
    # extracción (PlazoRelativoExtracted / DurationUnit) -- add_business_days
    # ya sabe convertirlas a fecha (horas: redondeo hacia arriba a días
    # completos; meses/años: aritmética calendario). day_type no aplica a
    # estas tres, se salta la validación 6 para ellas.
    if deadline.unit not in {"días", "horas", "meses", "años"}:
        error_msg = (
            f"Unidad '{deadline.unit}' no soportada. "
            "Valores permitidos: 'días', 'horas', 'meses', 'años'."
        )
        errors.append(error_msg)
        logger.error(error_msg)
    
    # 5. Validar dirección (2026-09-01): el motor de cálculo solo sabe
    # sumar días hacia adelante desde el trigger. "antes_de"/"hasta"
    # implicarían calcular hacia atrás -- `add_business_days` no lo soporta
    # (rechaza días negativos a propósito). El Deadline SÍ se materializa
    # para estas direcciones (ver `_VALID_DIRECTIONS` en
    # `timeline/materializer.py` -- antes se descartaba el plazo entero, lo
    # que hacía perder la relación completa cuando el LLM etiquetaba mal la
    # dirección entre corridas), pero acá se frena ANTES de calcular una
    # fecha hacia adelante que sería incorrecta para un plazo hacia atrás.
    if deadline.direccion in {"hasta", "antes_de"}:
        target_name = target_event.name if target_event else deadline.name
        error_msg = (
            f"Dirección '{deadline.direccion}' de '{target_name}' requiere calcular "
            "hacia atrás desde el disparador -- todavía no está implementado. "
            "Cargá la fecha a mano mientras tanto."
        )
        errors.append(error_msg)
        logger.info(error_msg)

    # 6. Validar day_type (AC1, AC3). Solo aplica cuando unit="días" -- para
    # "horas"/"meses" el day_type es irrelevante (el pliego no distingue
    # "horas hábiles" ni "meses corridos" en este dominio) y no debe bloquear
    # el cálculo.
    if deadline.unit == "días":
        if deadline.day_type == "no_especificado":
            error_msg = (
                "Tipo de día no especificado en documento fuente. "
                "No se puede calcular fecha sin saber si son días corridos o hábiles."
            )
            errors.append(error_msg)
            logger.warning(error_msg)
        elif deadline.day_type not in ["corridos", "hábiles"]:
            error_msg = (
                f"day_type '{deadline.day_type}' inválido. "
                "Valores permitidos: 'corridos', 'hábiles'."
            )
            errors.append(error_msg)
            logger.error(error_msg)
    
    # Warnings (no impiden cálculo pero son informativos)
    if deadline.calculation_status == "error":
        warning_msg = (
            f"Este deadline tiene un error previo de cálculo: {deadline.calculation_error}"
        )
        warnings.append(warning_msg)
        logger.info(warning_msg)
    
    # Resultado (AC2)
    is_valid = len(errors) == 0
    
    if is_valid:
        logger.info(f"Deadline {deadline.deadline_id} pasó validación exitosamente")
    else:
        logger.warning(
            f"Deadline {deadline.deadline_id} falló validación con {len(errors)} errores"
        )
    
    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )
