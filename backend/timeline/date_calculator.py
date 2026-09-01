"""
Motor de cálculo determinístico de fechas.

Este módulo implementa funciones puras de cálculo de fechas
basadas en días corridos y días hábiles.

IMPORTANTE: NO usar LLMs aquí - solo matemática pura y determinística.
Los LLMs extraen la estructura, este código hace el cálculo.
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def add_business_days(
    start_date: date,
    days: int,
    day_type: str
) -> date:
    """
    Suma días a una fecha base según el tipo especificado.
    
    Esta es una función pura sin side-effects. El cálculo es
    completamente determinístico.
    
    Args:
        start_date: Fecha de inicio (datetime.date)
        days: Número de días a sumar (puede ser 0)
        day_type: Tipo de días a sumar. Valores válidos:
            - "corridos": días calendario consecutivos (incluye fines de semana)
            - "hábiles": días laborables (excluye sábados y domingos)
            - "no_especificado": NO es válido - debe fallar
    
    Returns:
        date: Fecha calculada después de sumar los días especificados
    
    Raises:
        ValueError: Si day_type es "no_especificado" o un valor inválido
    
    Note:
        Para "hábiles", actualmente solo excluye fines de semana.
        Los feriados nacionales NO están implementados (AR4 - mejora futura).
    
    Examples:
        >>> from datetime import date
        >>> add_business_days(date(2026, 9, 10), 45, "corridos")
        datetime.date(2026, 10, 25)
        
        >>> add_business_days(date(2026, 9, 10), 5, "hábiles")
        datetime.date(2026, 9, 17)
        
        >>> add_business_days(date(2026, 9, 10), 0, "corridos")
        datetime.date(2026, 9, 10)
    """
    # Validación: días no pueden ser negativos (PATCH: infinite loop)
    if days < 0:
        raise ValueError(
            f"days debe ser no-negativo, recibido: {days}. "
            "No se pueden calcular fechas hacia atrás."
        )
    
    # Validación: day_type no puede ser "no_especificado" (PATCH: mover antes de return early)
    if day_type == "no_especificado":
        raise ValueError(
            "No se puede calcular fecha con day_type='no_especificado'. "
            "El tipo de día debe estar explícito en el documento."
        )
    
    # Caso especial: 0 días retorna la fecha original
    if days == 0:
        return start_date
    
    # Cálculo de días corridos
    if day_type == "corridos":
        # Días corridos = días calendario consecutivos
        # No excluye fines de semana ni feriados
        return start_date + timedelta(days=days)
    
    # Cálculo de días hábiles (implementado en story 17-2)
    elif day_type == "hábiles":
        # Log de limitación (AR4) - PATCH: cambiar a DEBUG para evitar flood
        logger.debug(
            f"Calculando {days} días hábiles desde {start_date}. "
            "NOTA: Solo excluye fines de semana, feriados NO implementados (AR4)."
        )
        
        current = start_date
        days_added = 0
        
        while days_added < days:
            current += timedelta(days=1)
            # Excluir sábado (5) y domingo (6)
            # weekday(): Lunes=0, Martes=1, ..., Viernes=4, Sábado=5, Domingo=6
            if current.weekday() < 5:  # Lunes a Viernes
                days_added += 1
        
        return current
    
    # Valor inválido
    else:
        raise ValueError(
            f"day_type inválido: '{day_type}'. "
            f"Valores válidos: 'corridos', 'hábiles'"
        )
