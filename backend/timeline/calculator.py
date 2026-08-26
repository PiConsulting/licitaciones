"""
Motor de cálculo determinístico de fechas para Timeline (Épica 17).

Implementa:
- Cálculo de días corridos (17-1)
- Cálculo de días hábiles (17-2)
- Motor de recálculo en cascada (17-3)
- Validación de plazos antes del cálculo (17-4)
"""
import logging
from datetime import date, timedelta, UTC, datetime
from typing import Literal

from timeline.models import DireccionTemporal, Event, Deadline

logger = logging.getLogger(__name__)

# Límite de iteraciones para evitar loops infinitos en cascada.
# 100 iteraciones debería ser suficiente para cadenas profundas sin ciclos.
MAX_ITERATIONS = 100


class ValidationError(Exception):
    """Error de validación en cálculos de fechas."""
    pass


class CircularDependencyError(Exception):
    """Error por dependencia circular en el grafo de eventos/plazos."""
    pass


def calcular_dias_corridos(
    fecha_base: date,
    duracion: int,
    direccion: DireccionTemporal
) -> date:
    """
    Calcula una fecha sumando/restando días corridos (calendario).
    
    Los días corridos cuentan TODOS los días del calendario, incluyendo
    fines de semana y feriados.
    
    Args:
        fecha_base: Fecha desde/hasta la cual se cuenta
        duracion: Cantidad de días a sumar/restar (debe ser >= 0)
        direccion: Dirección temporal del cálculo:
            - "desde" o "hasta" o "después_de": suma días hacia adelante
            - "antes_de": resta días hacia atrás
    
    Returns:
        Fecha calculada
    
    Raises:
        ValidationError: Si duración es negativa o dirección inválida
    
    Examples:
        >>> calcular_dias_corridos(date(2026, 1, 15), 10, "desde")
        date(2026, 1, 25)
        
        >>> calcular_dias_corridos(date(2026, 1, 15), 10, "antes_de")
        date(2026, 1, 5)
    """
    if duracion < 0:
        raise ValidationError("La duración no puede ser negativa")
    
    if direccion not in ["desde", "hasta", "antes_de", "después_de"]:
        raise ValidationError(f"Dirección temporal inválida: {direccion}")
    
    # Direcciones hacia adelante: suma días
    if direccion in ["desde", "hasta", "después_de"]:
        return fecha_base + timedelta(days=duracion)
    
    # Dirección hacia atrás: resta días
    else:  # antes_de
        return fecha_base - timedelta(days=duracion)


def calcular_dias_habiles(
    fecha_base: date,
    duracion: int,
    direccion: DireccionTemporal
) -> date:
    """
    Calcula una fecha sumando/restando días hábiles (lunes a viernes).
    
    Los días hábiles excluyen sábados y domingos. No considera feriados
    (esa lógica se puede agregar después si el proyecto lo requiere).
    
    Reglas:
    - Si fecha_base cae en fin de semana y duracion > 0 hacia adelante,
      el conteo comienza desde el lunes siguiente.
    - Si fecha_base cae en fin de semana y duracion > 0 hacia atrás,
      el conteo comienza desde el viernes anterior.
    - Si duracion == 0 y fecha_base es hábil, retorna fecha_base.
    - Si duracion == 0 y fecha_base es fin de semana, avanza/retrocede
      al día hábil más cercano según la dirección.
    
    Args:
        fecha_base: Fecha desde/hasta la cual se cuenta
        duracion: Cantidad de días hábiles a sumar/restar (debe ser >= 0)
        direccion: Dirección temporal del cálculo
    
    Returns:
        Fecha calculada (siempre será un día hábil)
    
    Raises:
        ValidationError: Si duración es negativa o dirección inválida
    
    Examples:
        >>> calcular_dias_habiles(date(2026, 1, 5), 3, "desde")  # Lunes
        date(2026, 1, 8)  # Jueves
        
        >>> calcular_dias_habiles(date(2026, 1, 9), 1, "desde")  # Viernes
        date(2026, 1, 12)  # Lunes (salta fin de semana)
    """
    if duracion < 0:
        raise ValidationError("La duración no puede ser negativa")
    
    if direccion not in ["desde", "hasta", "antes_de", "después_de"]:
        raise ValidationError(f"Dirección temporal inválida: {direccion}")
    
    # Determinar si vamos hacia adelante o atrás
    hacia_adelante = direccion in ["desde", "hasta", "después_de"]
    
    # Ajustar fecha base si cae en fin de semana
    fecha_actual = _ajustar_a_dia_habil(fecha_base, hacia_adelante)
    
    # Si duración es 0, ya tenemos la respuesta
    if duracion == 0:
        return fecha_actual
    
    # Contar días hábiles
    dias_contados = 0
    incremento = 1 if hacia_adelante else -1
    
    while dias_contados < duracion:
        fecha_actual += timedelta(days=incremento)
        
        # Solo contar si es día hábil (lunes=0 a viernes=4)
        if fecha_actual.weekday() < 5:
            dias_contados += 1
    
    return fecha_actual


def _ajustar_a_dia_habil(fecha: date, hacia_adelante: bool) -> date:
    """
    Ajusta una fecha al día hábil más cercano si cae en fin de semana.
    
    Args:
        fecha: Fecha a ajustar
        hacia_adelante: Si True, ajusta hacia lunes siguiente.
                       Si False, ajusta hacia viernes anterior.
    
    Returns:
        Fecha ajustada (o la misma si ya es día hábil)
    """
    dia_semana = fecha.weekday()  # 0=lunes, 6=domingo
    
    # Si ya es día hábil, retornar sin cambios
    if dia_semana < 5:  # lunes a viernes
        return fecha
    
    # Fin de semana: ajustar según dirección
    if hacia_adelante:
        # Sábado (5) -> +2 días = Lunes
        # Domingo (6) -> +1 día = Lunes
        dias_hasta_lunes = 7 - dia_semana + 0  # 0 es lunes
        return fecha + timedelta(days=dias_hasta_lunes)
    else:
        # Sábado (5) -> -1 día = Viernes
        # Domingo (6) -> -2 días = Viernes
        dias_hasta_viernes = dia_semana - 4  # 4 es viernes
        return fecha - timedelta(days=dias_hasta_viernes)


def validar_plazo_antes_calculo(
    plazo: Deadline,
    eventos_disponibles: dict[str, Event]
) -> None:
    """
    Valida que un plazo tenga todos los datos necesarios para cálculo.
    
    Reglas de validación:
    - trigger_event_id debe existir y no ser None
    - El evento trigger debe existir en eventos_disponibles
    - Si day_type es "hábiles", direccion es requerida
    
    Args:
        plazo: Deadline a validar
        eventos_disponibles: Dict {event_id: Event} con eventos disponibles
    
    Raises:
        ValidationError: Si falla alguna regla de validación
    """
    if not plazo.trigger_event_id:
        raise ValidationError(
            f"Plazo {plazo.deadline_id}: falta evento disparador (trigger_event_id requerido)"
        )
    
    if plazo.trigger_event_id not in eventos_disponibles:
        raise ValidationError(
            f"Plazo {plazo.deadline_id}: evento disparador '{plazo.trigger_event_id}' no existe"
        )
    
    if plazo.day_type == "hábiles" and not plazo.direccion:
        raise ValidationError(
            f"Plazo {plazo.deadline_id}: dirección temporal requerida para días hábiles"
        )
    
    # Solo soportamos unit="días" por ahora
    if plazo.unit != "días":
        raise ValidationError(
            f"Plazo {plazo.deadline_id}: unidad '{plazo.unit}' no soportada (solo 'días' implementado)"
        )


def calcular_fechas_cascada(
    eventos: list[Event],
    plazos: list[Deadline]
) -> tuple[list[Event], list[Deadline]]:
    """
    Motor de recálculo determinístico de fechas en cascada (17-3).
    
    Calcula fechas de eventos y deadlines siguiendo las dependencias del
    grafo. Procesa iterativamente hasta que no haya más cambios o detecte
    un deadlock.
    
    Algoritmo:
    1. Construir grafo de dependencias (trigger -> target)
    2. Detectar ciclos (lanzar CircularDependencyError)
    3. Iterar mientras haya cambios:
       - Procesar cada plazo que tenga trigger con fecha
       - Calcular deadline_date y asignar a target_event_id si aplica
       - Repetir hasta convergencia (no más cambios) o máximo iteraciones
    4. Marcar estados: calculated, pending o error
    
    Args:
        eventos: Lista de eventos a procesar
        plazos: Lista de plazos a procesar
    
    Returns:
        Tupla (eventos_actualizados, plazos_actualizados)
    
    Raises:
        CircularDependencyError: Si hay ciclos en el grafo de dependencias
    """
    # Copiar para no mutar los originales
    try:
        eventos_dict = {e.event_id: Event(**e.model_dump()) for e in eventos}
        plazos_dict = {d.deadline_id: Deadline(**d.model_dump()) for d in plazos}
    except Exception as e:
        raise ValidationError(f"Error copiando modelos: {e}")
    
    # Construir grafo de dependencias para detectar ciclos
    grafo = {}  # event_id -> [event_ids que dependen de él]
    for plazo in plazos_dict.values():
        if plazo.trigger_event_id and plazo.target_event_id:
            # Detectar self-loops
            if plazo.trigger_event_id == plazo.target_event_id:
                raise CircularDependencyError(
                    f"Auto-referencia detectada en plazo {plazo.deadline_id}: "
                    f"trigger y target son el mismo evento '{plazo.trigger_event_id}'"
                )
            
            if plazo.trigger_event_id not in grafo:
                grafo[plazo.trigger_event_id] = []
            grafo[plazo.trigger_event_id].append(plazo.target_event_id)
    
    # Detectar ciclos con DFS
    visitados = set()
    en_pila = set()
    
    def tiene_ciclo(nodo: str) -> bool:
        if nodo in en_pila:
            return True
        if nodo in visitados:
            return False
        
        visitados.add(nodo)
        en_pila.add(nodo)
        
        for vecino in grafo.get(nodo, []):
            if tiene_ciclo(vecino):
                return True
        
        en_pila.remove(nodo)
        return False
    
    for event_id in eventos_dict.keys():
        if tiene_ciclo(event_id):
            raise CircularDependencyError(
                f"Dependencia circular detectada en el grafo de eventos/plazos"
            )
    
    # Procesar plazos iterativamente hasta convergencia
    # Capturar timestamp una sola vez para consistencia
    timestamp_calculo = datetime.now(UTC)
    errores_validacion = 0
    plazos_sin_trigger_fecha = 0
    
    for iteracion in range(MAX_ITERATIONS):
        hubo_cambios = False
        
        # Dict para acumular fechas candidatas por evento target en esta iteración
        fechas_candidatas = {}  # target_event_id -> [fechas calculadas]
        
        for plazo in plazos_dict.values():
            # Si ya está calculado, skip
            if plazo.calculation_status == "calculated":
                continue
            
            try:
                # Validar plazo
                validar_plazo_antes_calculo(plazo, eventos_dict)
                
                # Obtener evento trigger
                trigger_event = eventos_dict.get(plazo.trigger_event_id)
                if not trigger_event:
                    plazo.calculation_status = "error"
                    plazo.calculation_error = f"Evento trigger {plazo.trigger_event_id} no encontrado"
                    errores_validacion += 1
                    continue
                
                # Si el trigger no tiene fecha, no podemos calcular
                if trigger_event.event_date is None:
                    # No es error, solo pendiente
                    plazo.calculation_status = "pending"
                    plazo.calculation_error = "Evento disparador sin fecha asignada"
                    plazos_sin_trigger_fecha += 1
                    continue
                
                # Calcular fecha del deadline según tipo de día
                if plazo.day_type == "hábiles":
                    fecha_calculada = calcular_dias_habiles(
                        trigger_event.event_date,
                        plazo.duration,
                        plazo.direccion or "desde"
                    )
                else:  # corridos o no_especificado
                    fecha_calculada = calcular_dias_corridos(
                        trigger_event.event_date,
                        plazo.duration,
                        plazo.direccion or "desde"
                    )
                
                # Actualizar deadline
                plazo.deadline_date = fecha_calculada
                plazo.calculation_status = "calculated"
                plazo.calculation_error = None
                plazo.updated_at = timestamp_calculo
                hubo_cambios = True
                
                # Si tiene target_event_id, validar que existe y acumular fecha candidata
                if plazo.target_event_id:
                    if plazo.target_event_id not in eventos_dict:
                        plazo.calculation_status = "error"
                        plazo.calculation_error = f"Evento target '{plazo.target_event_id}' no existe"
                        errores_validacion += 1
                    else:
                        if plazo.target_event_id not in fechas_candidatas:
                            fechas_candidatas[plazo.target_event_id] = []
                        fechas_candidatas[plazo.target_event_id].append(fecha_calculada)
            
            except ValidationError as e:
                plazo.calculation_status = "error"
                plazo.calculation_error = str(e)
                errores_validacion += 1
        
        # Asignar fechas a eventos target (la más temprana si hay múltiples)
        for target_id, fechas in fechas_candidatas.items():
            if target_id in eventos_dict:
                evento_target = eventos_dict[target_id]
                # Solo actualizar si el evento está pendiente
                if evento_target.event_date is None:
                    evento_target.event_date = min(fechas)
                    evento_target.date_source = "calculated"
                    evento_target.status = "confirmed"
                    evento_target.updated_at = timestamp_calculo
                    hubo_cambios = True
        
        # Si no hubo cambios en esta iteración, convergimos
        if not hubo_cambios:
            break
    
    # Warning si alcanzamos MAX_ITERATIONS sin convergencia completa
    if iteracion == MAX_ITERATIONS - 1 and hubo_cambios:
        logger.warning(
            f"MAX_ITERATIONS ({MAX_ITERATIONS}) alcanzado sin convergencia completa. "
            f"Errores: {errores_validacion}, Plazos pendientes: {plazos_sin_trigger_fecha}"
        )
    
    # Log summary si hubo errores
    if errores_validacion > 0 or plazos_sin_trigger_fecha > 0:
        logger.info(
            f"Cascada completada con {errores_validacion} errores y "
            f"{plazos_sin_trigger_fecha} plazos pendientes por falta de fecha trigger"
        )
    
    return list(eventos_dict.values()), list(plazos_dict.values())
