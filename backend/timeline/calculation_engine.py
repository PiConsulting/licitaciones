"""
Motor de recálculo de fechas en cascada.

Este módulo implementa la lógica de recálculo automático de fechas de eventos
que dependen de otros eventos a través de deadlines. Cuando cambia la fecha
de un evento, todos los eventos que dependen de él se recalculan recursivamente.

IMPORTANTE: Este módulo NO usa LLMs - solo matemática determinística y
propagación de dependencias.
"""
import logging
from datetime import date

from timeline.date_calculator import add_business_days
from timeline.models import Deadline, Event
from timeline.service import TimelineService
from timeline.validation import validate_deadline_for_calculation, RecalculationResult

logger = logging.getLogger(__name__)


def recalculate_dependent_dates(
    service: TimelineService,
    analysis_id: str,
    event_id: str,
    user_id: str | None = None,
    visited: set[str] | None = None,
    max_depth: int = 1000
) -> RecalculationResult:
    """
    Recalcula fechas de todos los eventos que dependen del evento dado.
    Propaga cambios recursivamente en cascada.
    
    Esta función implementa un algoritmo recursivo que:
    1. Encuentra todos los deadlines que usan event_id como trigger
    2. Para cada deadline, calcula la nueva fecha del evento target
    3. Actualiza el deadline y el evento target
    4. Recursivamente recalcula dependientes del evento target (cascada)
    5. Detecta ciclos de dependencia y los reporta como errores
    
    Args:
        service: Instancia de TimelineService para acceso a datos
        analysis_id: ID del análisis
        event_id: ID del evento cuyas dependencias recalcular
        user_id: ID del usuario (opcional para tests con mocks)
        visited: Set de event_ids ya visitados (para detectar ciclos)
        max_depth: Profundidad máxima de recursión (default 1000)
    
    Returns:
        RecalculationResult con:
            - events_updated: int - Número de eventos actualizados
            - errors: list[str] - Lista de errores encontrados
    
    Raises:
        No lanza excepciones - todos los errores se retornan en el resultado
    
    Examples:
        >>> service = TimelineService(db)
        >>> result = recalculate_dependent_dates(service, "analysis-1", "adj-1", "user-123")
        >>> print(result.events_updated, result.errors)
        3 []
    """
    if visited is None:
        visited = set()

    if len(visited) > max_depth:
        error = f"Max recursion depth ({max_depth}) exceeded. Check for circular dependencies or very deep chains."
        logger.error(error)
        return RecalculationResult(events_updated=0, errors=[error])
    
    if event_id in visited:
        error = f"Ciclo de dependencia detectado en cadena: {visited} -> {event_id}"
        logger.error(error)
        return RecalculationResult(events_updated=0, errors=[error])

    visited.add(event_id)

    trigger_event = service.get_event(event_id, analysis_id, user_id)

    if not trigger_event:
        error = f"Evento {event_id} no existe"
        logger.warning(error)
        return RecalculationResult(events_updated=0, errors=[error])
    
    if not trigger_event.event_date:
        error = f"Evento {event_id} no tiene fecha asignada"
        logger.info(error)

        all_deadlines = service.list_deadlines(analysis_id, user_id)
        for dl in all_deadlines:
            if dl.trigger_event_id == event_id and dl.calculation_status != "pending":
                dl.calculation_status = "pending"
                dl.calculation_error = f"Esperando fecha de evento '{event_id}'"
                service.update_deadline(dl, user_id)
        
        return RecalculationResult(events_updated=0, errors=[error])

    all_deadlines = service.list_deadlines(analysis_id, user_id)
    dependent_deadlines = [
        dl for dl in all_deadlines 
        if dl.trigger_event_id == event_id and not dl.deleted
    ]
    
    logger.info(
        f"Recalculando {len(dependent_deadlines)} deadlines "
        f"dependientes de evento {event_id}"
    )
    
    stats = RecalculationResult(events_updated=0, errors=[])

    for deadline in dependent_deadlines:
        try:
            validation = validate_deadline_for_calculation(service, analysis_id, deadline, user_id)
            if not validation.is_valid:
                deadline.calculation_status = "error"
                deadline.calculation_error = "; ".join(validation.errors)
                service.update_deadline(deadline, user_id)
                stats.errors.extend(validation.errors)
                continue
            
            # Redundant with validate_deadline_for_calculation, kept explicit; only unit="días" uses day_type.
            if deadline.unit == "días" and deadline.day_type == "no_especificado":
                deadline.calculation_status = "error"
                deadline.calculation_error = (
                    "Tipo de día no especificado en documento fuente"
                )
                service.update_deadline(deadline, user_id)

                error_msg = (
                    f"Deadline {deadline.deadline_id}: tipo de día no especificado"
                )
                logger.warning(error_msg)
                stats.errors.append(error_msg)
                continue
            
            # Fetched before calculating: cascade must not overwrite a user-fixed date (date_source="user_input").
            target_event = service.get_event(deadline.target_event_id, analysis_id, user_id)
            if not target_event:
                error_msg = (
                    f"Evento target {deadline.target_event_id} no encontrado "
                    f"para deadline {deadline.deadline_id}"
                )
                logger.error(error_msg)
                stats.errors.append(error_msg)
                continue

            if target_event.deleted:
                logger.warning(f"Evento target {target_event.event_id} está eliminado, saltando actualización")
                continue

            calculated = add_business_days(
                trigger_event.event_date,
                deadline.duration,
                deadline.day_type,
                unit=deadline.unit,
            )

            logger.info(
                f"Calculado {deadline.deadline_id}: "
                f"{trigger_event.event_date} + {deadline.duration} {deadline.day_type} "
                f"= {calculated}"
            )

            if target_event.date_source == "user_input":
                # Keep deadline_date synced to the event's real (user-set) date, not the recalculated one.
                if (
                    deadline.deadline_date != target_event.event_date
                    or deadline.calculation_status != "calculated"
                    or deadline.calculation_error is not None
                ):
                    deadline.deadline_date = target_event.event_date
                    deadline.calculation_status = "calculated"
                    deadline.calculation_error = None
                    service.update_deadline(deadline, user_id)

                logger.info(
                    f"Evento {target_event.event_id} tiene fecha fijada por el "
                    "usuario (date_source=user_input) -- se preserva, no se recalcula."
                )

                # Cascade continues: dependents of this target still recalc from its real (user-set) date.
                cascaded = recalculate_dependent_dates(
                    service,
                    analysis_id,
                    deadline.target_event_id,
                    user_id,
                    visited.copy()
                )
                stats.events_updated += cascaded.events_updated
                stats.errors.extend(cascaded.errors)
                continue

            deadline.deadline_date = calculated
            deadline.calculation_status = "calculated"
            deadline.calculation_error = None
            service.update_deadline(deadline, user_id)

            target_event.event_date = calculated
            target_event.date_source = "calculated"
            service.update_event(target_event, user_id)
            stats.events_updated += 1

            logger.info(f"Actualizado evento {target_event.event_id} con fecha {calculated}")

            # Copy visited to avoid shared mutation across recursive branches.
            cascaded = recalculate_dependent_dates(
                service,
                analysis_id,
                deadline.target_event_id,
                user_id,
                visited.copy()
            )

            stats.events_updated += cascaded.events_updated
            stats.errors.extend(cascaded.errors)
            
        except ValueError as e:
            error_msg = f"Error de validación en deadline {deadline.deadline_id}: {str(e)}"
            logger.warning(error_msg)
            stats.errors.append(error_msg)

            deadline.calculation_status = "error"
            deadline.calculation_error = str(e)
            try:
                service.update_deadline(deadline, user_id)
            except Exception as update_error:
                logger.exception(f"Error actualizando deadline con error: {update_error}")
        except Exception as e:
            error_msg = f"Error inesperado calculando deadline {deadline.deadline_id}: {str(e)}"
            logger.exception(error_msg)
            stats.errors.append(error_msg)

            deadline.calculation_status = "error"
            deadline.calculation_error = str(e)
            try:
                service.update_deadline(deadline, user_id)
            except Exception as update_error:
                logger.exception(f"Error actualizando deadline con error: {update_error}")
    
    logger.info(
        f"Recálculo completado para evento {event_id}: "
        f"{stats.events_updated} eventos actualizados, "
        f"{len(stats.errors)} errores"
    )
    
    return stats
