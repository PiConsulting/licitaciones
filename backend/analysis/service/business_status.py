"""Transiciones y actualización de `Analysis.business_status` (Epic FE5, Story FE5.2/FE5.3).

La máquina de estados de abajo es la que la usuaria confirmó directamente al pedir esta
implementación -- Story FE5.2 quedó formalmente en el backlog como "pendiente de confirmación
con el negocio", pero la respuesta ya llegó y es la que se codifica acá:

    EN_ANALISIS -> PENDIENTE_DECISION -> (NO_APROBADA | EN_REVISION) -> PRESENTADA
    -> (GANADA | PERDIDA)

`NO_APROBADA` puede reabrirse hacia `PENDIENTE_DECISION` o `EN_REVISION`. No hay un estado
`APROBADA` explícito: la aprobación es implícita al pasar de `PENDIENTE_DECISION` a
`EN_REVISION`.

`GANADA`/`PERDIDA` se modelan acá como terminales (sin transiciones salientes) por ser la
lectura estándar de un pipeline comercial ganado/perdido -- esto NO fue confirmado
explícitamente por la usuaria. Si el negocio pide reabrir una licitación ganada/perdida más
adelante, la única línea a tocar es `BUSINESS_STATUS_TRANSITIONS`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from analysis.models import Analysis, BusinessStatus, BusinessStatusHistory

BUSINESS_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    BusinessStatus.EN_ANALISIS.value: frozenset({BusinessStatus.PENDIENTE_DECISION.value}),
    BusinessStatus.PENDIENTE_DECISION.value: frozenset(
        {BusinessStatus.NO_APROBADA.value, BusinessStatus.EN_REVISION.value}
    ),
    BusinessStatus.NO_APROBADA.value: frozenset(
        {BusinessStatus.PENDIENTE_DECISION.value, BusinessStatus.EN_REVISION.value}
    ),
    BusinessStatus.EN_REVISION.value: frozenset({BusinessStatus.PRESENTADA.value}),
    BusinessStatus.PRESENTADA.value: frozenset(
        {BusinessStatus.GANADA.value, BusinessStatus.PERDIDA.value}
    ),
    BusinessStatus.GANADA.value: frozenset(),
    BusinessStatus.PERDIDA.value: frozenset(),
}


def is_valid_business_status_transition(current: str | None, target: str) -> bool:
    """Sin estado previo, la única entrada válida al flujo es `EN_ANALISIS`."""
    if current is None:
        return target == BusinessStatus.EN_ANALISIS.value
    if current == target:
        return False
    return target in BUSINESS_STATUS_TRANSITIONS.get(current, frozenset())


def update_business_status(
    db: Session,
    *,
    analysis: Analysis,
    target_status: str,
    user_id: str,
    note: str | None = None,
) -> BusinessStatusHistory:
    """Aplica el cambio y registra el historial auditable (Story FE5.1) en una misma transacción."""
    previous_status = analysis.business_status
    now = datetime.now(UTC)

    analysis.business_status = target_status
    analysis.updated_at = now

    history_entry = BusinessStatusHistory(
        analysis_id=analysis.id,
        previous_status=previous_status,
        new_status=target_status,
        changed_by=user_id,
        changed_at=now,
        note=note,
    )
    db.add(history_entry)
    db.commit()
    db.refresh(history_entry)
    return history_entry
