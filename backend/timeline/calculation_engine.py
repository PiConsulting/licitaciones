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
    max_depth: int = 1000  # F6 fix: límite de profundidad
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
    # Inicializar set de visitados para detectar ciclos
    if visited is None:
        visited = set()
    
    # F6 fix: Detectar profundidad excesiva
    if len(visited) > max_depth:
        error = f"Max recursion depth ({max_depth}) exceeded. Check for circular dependencies or very deep chains."
        logger.error(error)
        return RecalculationResult(events_updated=0, errors=[error])
    
    # Detectar ciclos
    if event_id in visited:
        error = f"Ciclo de dependencia detectado en cadena: {visited} -> {event_id}"
        logger.error(error)
        return RecalculationResult(events_updated=0, errors=[error])
    
    # Marcar este evento como visitado
    visited.add(event_id)
    
    # Obtener evento base (trigger)
    trigger_event = service.get_event(event_id, analysis_id, user_id)
    
    # Validar que el evento existe y tiene fecha
    if not trigger_event:
        error = f"Evento {event_id} no existe"
        logger.warning(error)
        return RecalculationResult(events_updated=0, errors=[error])
    
    if not trigger_event.event_date:
        error = f"Evento {event_id} no tiene fecha asignada"
        logger.info(error)
        
        # PATCH: Marcar deadlines dependientes como pending
        all_deadlines = service.list_deadlines(analysis_id, user_id)
        for dl in all_deadlines:
            if dl.trigger_event_id == event_id and dl.calculation_status != "pending":
                dl.calculation_status = "pending"
                dl.calculation_error = f"Esperando fecha de evento '{event_id}'"
                service.update_deadline(dl, user_id)
        
        return RecalculationResult(events_updated=0, errors=[error])
    
    # Buscar todos los deadlines que dependen de este evento
    all_deadlines = service.list_deadlines(analysis_id, user_id)
    dependent_deadlines = [
        dl for dl in all_deadlines 
        if dl.trigger_event_id == event_id and not dl.deleted
    ]
    
    logger.info(
        f"Recalculando {len(dependent_deadlines)} deadlines "
        f"dependientes de evento {event_id}"
    )
    
    # Estadísticas de ejecución
    stats = RecalculationResult(events_updated=0, errors=[])
    
    # Procesar cada deadline dependiente
    for deadline in dependent_deadlines:
        try:
            # PATCH: Validación defensiva antes de calcular
            validation = validate_deadline_for_calculation(service, analysis_id, deadline, user_id)
            if not validation.is_valid:
                deadline.calculation_status = "error"
                deadline.calculation_error = "; ".join(validation.errors)
                service.update_deadline(deadline, user_id)
                stats.errors.extend(validation.errors)
                continue
            
            # AC2: Validar que day_type esté especificado (redundante con validation, pero explícito)
            if deadline.day_type == "no_especificado":
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
            
            # Obtener el evento target ANTES de calcular: si el usuario ya
            # fijó su fecha a mano (date_source="user_input"), la cascada no
            # debe pisarla -- ver AddDateModal/EditDateModal, que ya le
            # prometen al usuario que "futuros recálculos no la
            # sobrescribirán" cuando edita una fecha calculada. Antes de este
            # fix esa promesa no se cumplía: acá siempre se sobreescribía.
            target_event = service.get_event(deadline.target_event_id, analysis_id, user_id)
            if not target_event:
                error_msg = (
                    f"Evento target {deadline.target_event_id} no encontrado "
                    f"para deadline {deadline.deadline_id}"
                )
                logger.error(error_msg)
                stats.errors.append(error_msg)
                continue

            # PATCH: No actualizar eventos eliminados
            if target_event.deleted:
                logger.warning(f"Evento target {target_event.event_id} está eliminado, saltando actualización")
                continue

            # Calcular fecha usando el motor determinístico
            calculated = add_business_days(
                trigger_event.event_date,
                deadline.duration,
                deadline.day_type
            )

            logger.info(
                f"Calculado {deadline.deadline_id}: "
                f"{trigger_event.event_date} + {deadline.duration} {deadline.day_type} "
                f"= {calculated}"
            )

            if target_event.date_source == "user_input":
                # Evento fijado a mano por el usuario: no tocamos su fecha.
                # El deadline sí se mantiene sincronizado con la fecha REAL
                # vigente del evento (no con el valor recalculado), para no
                # mostrar dos números distintos para el mismo hito.
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

                # La cascada sigue: eventos que dependen de ESTE target deben
                # recalcularse en base a su fecha real (la que el usuario cargó).
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

            # Actualizar deadline con fecha calculada
            deadline.deadline_date = calculated
            deadline.calculation_status = "calculated"
            deadline.calculation_error = None
            service.update_deadline(deadline, user_id)

            # Actualizar evento target con la fecha calculada
            target_event.event_date = calculated
            target_event.date_source = "calculated"
            service.update_event(target_event, user_id)
            stats.events_updated += 1

            logger.info(f"Actualizado evento {target_event.event_id} con fecha {calculated}")

            # Recalcular dependientes del evento target (cascada)
            # Copiar visited para evitar mutación compartida entre ramas
            cascaded = recalculate_dependent_dates(
                service,
                analysis_id,
                deadline.target_event_id,
                user_id,
                visited.copy()
            )

            # Acumular estadísticas de la recursión
            stats.events_updated += cascaded.events_updated
            stats.errors.extend(cascaded.errors)
            
        except ValueError as e:
            # PATCH: Catch específico para errores de validación/cálculo
            error_msg = f"Error de validación en deadline {deadline.deadline_id}: {str(e)}"
            logger.warning(error_msg)
            stats.errors.append(error_msg)
            
            # Marcar deadline como error
            deadline.calculation_status = "error"
            deadline.calculation_error = str(e)
            try:
                service.update_deadline(deadline, user_id)
            except Exception as update_error:
                logger.exception(f"Error actualizando deadline con error: {update_error}")
        except Exception as e:
            # Errores inesperados (base de datos, etc.)
            error_msg = f"Error inesperado calculando deadline {deadline.deadline_id}: {str(e)}"
            logger.exception(error_msg)
            stats.errors.append(error_msg)
            
            # Marcar deadline como error
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
