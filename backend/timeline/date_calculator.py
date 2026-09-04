"""
Motor de cálculo determinístico de fechas.

Este módulo implementa funciones puras de cálculo de fechas
basadas en días corridos, días hábiles, horas y meses.

IMPORTANTE: NO usar LLMs aquí - solo matemática pura y determinística.
Los LLMs extraen la estructura, este código hace el cálculo.
"""
import calendar
import logging
import math
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_VALID_UNITS = {"días", "horas", "meses", "años"}


def _add_months(start_date: date, months: int) -> date:
    """Suma meses calendario a una fecha, recortando el día al último día
    válido del mes de destino si hace falta (ej. 31 de enero + 1 mes = 28/29
    de febrero, no un error)."""
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_business_days(
    start_date: date,
    days: int,
    day_type: str,
    unit: str = "días",
) -> date:
    """
    Suma una duración a una fecha base según la unidad y el tipo de día
    especificados.

    Esta es una función pura sin side-effects. El cálculo es
    completamente determinístico.

    Args:
        start_date: Fecha de inicio (datetime.date)
        days: Cantidad a sumar, en la unidad indicada por `unit` (puede ser 0)
        day_type: Tipo de días a sumar, SOLO relevante cuando unit="días":
            - "corridos": días calendario consecutivos (incluye fines de semana)
            - "hábiles": días laborables (excluye sábados y domingos)
            - "no_especificado": NO es válido cuando unit="días" - debe fallar
        unit: Unidad de la duración. Valores válidos:
            - "días" (default): usa `day_type` para decidir corridos/hábiles
            - "horas": convierte a días de calendario completos (redondeo
              hacia arriba -- el modelo de Event solo guarda fecha, no hora,
              así que "3 horas" y "24 horas" caen ambas al día siguiente
              corrido; `day_type` se ignora, no aplica a horas)
            - "meses": suma meses calendario (ver `_add_months`); `day_type`
              se ignora, no aplica a meses

    Returns:
        date: Fecha calculada después de sumar la duración especificada

    Raises:
        ValueError: Si `unit` es inválida, o si `unit="días"` y `day_type`
            es "no_especificado" o un valor inválido

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

        >>> add_business_days(date(2026, 9, 10), 48, "no_especificado", unit="horas")
        datetime.date(2026, 9, 12)

        >>> add_business_days(date(2026, 1, 31), 1, "no_especificado", unit="meses")
        datetime.date(2026, 2, 28)
    """
    # Validación: la cantidad no puede ser negativa (PATCH: infinite loop)
    if days < 0:
        raise ValueError(
            f"days debe ser no-negativo, recibido: {days}. "
            "No se pueden calcular fechas hacia atrás."
        )

    if unit not in _VALID_UNITS:
        raise ValueError(
            f"unit inválida: '{unit}'. Valores válidos: {sorted(_VALID_UNITS)}"
        )

    # Caso especial: 0 de cualquier unidad retorna la fecha original
    if days == 0:
        return start_date

    # Horas: el Event solo guarda fecha (sin hora), así que se redondea
    # hacia arriba a días de calendario completos. day_type no aplica.
    if unit == "horas":
        equivalent_days = math.ceil(days / 24)
        return start_date + timedelta(days=equivalent_days)

    # Meses: aritmética calendario pura, day_type no aplica.
    if unit == "meses":
        return _add_months(start_date, days)

    # Años: mismo mecanismo que meses (12 meses por año), day_type no aplica.
    if unit == "años":
        return _add_months(start_date, days * 12)

    # unit == "días": el comportamiento de siempre, gobernado por day_type.

    # Validación: day_type no puede ser "no_especificado" (PATCH: mover antes de return early)
    if day_type == "no_especificado":
        raise ValueError(
            "No se puede calcular fecha con day_type='no_especificado'. "
            "El tipo de día debe estar explícito en el documento."
        )

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
