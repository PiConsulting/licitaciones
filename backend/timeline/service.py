"""
Servicios de persistencia CRUD para Timeline en PostgreSQL.

Operaciones CRUD para eventos y deadlines. La delegación a SQL vive en
`timeline/repository.py` -- este servicio solo orquesta autorización +
soft-delete + timestamps, igual que antes contra Cosmos.

SEGURIDAD: Todos los métodos validan que el user_id tenga ownership
del analysis_id antes de permitir operaciones.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from timeline import repository
from timeline.auth import validate_analysis_access
from timeline.models import Deadline, Event


class TimelineService:
    """Servicio de persistencia para eventos y deadlines en PostgreSQL."""

    def __init__(self, db: Session):
        """
        Inicializa el servicio con una sesión de SQLAlchemy.

        Args:
            db: Sesión de SQLAlchemy activa.
        """
        self.db = db

    def create_event(self, event: Event, user_id: str) -> Event:
        """
        Crea un nuevo evento.

        Args:
            event: Modelo Event a persistir
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Event creado

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, event.analysis_id, user_id)
        return repository.create_event(self.db, event)

    def get_event(self, event_id: str, analysis_id: str, user_id: str) -> Event | None:
        """
        Obtiene un evento por ID.

        Args:
            event_id: ID del evento (sin prefijo "event::")
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Event si existe, None si no se encuentra

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, analysis_id, user_id)
        return repository.get_event(self.db, event_id, analysis_id)

    def update_event(self, event: Event, user_id: str) -> Event:
        """
        Actualiza un evento existente.

        Args:
            event: Modelo Event con datos actualizados
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Event actualizado

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
            NoResultFound: Si el evento no existe
        """
        validate_analysis_access(self.db, event.analysis_id, user_id)
        event.updated_at = datetime.now(UTC)
        return repository.update_event(self.db, event)

    def delete_event(self, event_id: str, analysis_id: str, user_id: str) -> bool:
        """
        Soft delete de un evento (marca deleted=True).

        Args:
            event_id: ID del evento (sin prefijo)
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            True si se eliminó, False si no se encontró

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        event = self.get_event(event_id, analysis_id, user_id)
        if not event:
            return False

        event.deleted = True
        event.updated_at = datetime.now(UTC)
        self.update_event(event, user_id)
        return True

    def list_events(
        self,
        analysis_id: str,
        user_id: str,
        include_deleted: bool = False,
        include_hidden: bool = False,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[Event]:
        """
        Lista todos los eventos de un análisis.

        Args:
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)
            include_deleted: Si True, incluye eventos marcados como deleted
            include_hidden: Si True, incluye eventos marcados como hidden
                (ver `Event.hidden` -- ocultos "por el momento", no borrados)
            limit: Máximo número de resultados (None = sin límite)
            skip: Número de resultados a saltear (para paginación)

        Returns:
            Lista de eventos

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, analysis_id, user_id)
        return repository.list_events(
            self.db,
            analysis_id,
            include_deleted=include_deleted,
            include_hidden=include_hidden,
            limit=limit,
            skip=skip,
        )

    def set_event_hidden(
        self, event_id: str, analysis_id: str, user_id: str, hidden: bool
    ) -> Event | None:
        """
        Oculta o muestra un evento sin borrarlo (2026-09-01).

        Distinto del soft-delete (`delete_event`): el evento sigue existiendo
        y participando con normalidad del cálculo de fechas (un evento oculto
        puede seguir siendo trigger de un deadline de otro evento visible) --
        solo deja de contar en las estadísticas del timeline y en el panel de
        "fechas por cargar" del frontend mientras `hidden=True`.

        Args:
            event_id: ID del evento (sin prefijo)
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)
            hidden: True para ocultar, False para volver a mostrar

        Returns:
            Event actualizado, o None si no se encontró

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        event = self.get_event(event_id, analysis_id, user_id)
        if not event:
            return None

        event.hidden = hidden
        return self.update_event(event, user_id)

    def create_deadline(self, deadline: Deadline, user_id: str) -> Deadline:
        """
        Crea un nuevo deadline.

        Args:
            deadline: Modelo Deadline a persistir
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Deadline creado

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, deadline.analysis_id, user_id)
        return repository.create_deadline(self.db, deadline)

    def get_deadline(self, deadline_id: str, analysis_id: str, user_id: str) -> Deadline | None:
        """
        Obtiene un deadline por ID.

        Args:
            deadline_id: ID del deadline (sin prefijo "deadline::")
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Deadline si existe, None si no se encuentra

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, analysis_id, user_id)
        return repository.get_deadline(self.db, deadline_id, analysis_id)

    def update_deadline(self, deadline: Deadline, user_id: str) -> Deadline:
        """
        Actualiza un deadline existente.

        Args:
            deadline: Modelo Deadline con datos actualizados
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            Deadline actualizado

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, deadline.analysis_id, user_id)
        deadline.updated_at = datetime.now(UTC)
        return repository.update_deadline(self.db, deadline)

    def delete_deadline(self, deadline_id: str, analysis_id: str, user_id: str) -> bool:
        """
        Soft delete de un deadline.

        Args:
            deadline_id: ID del deadline (sin prefijo)
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)

        Returns:
            True si se eliminó, False si no se encontró

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        deadline = self.get_deadline(deadline_id, analysis_id, user_id)
        if not deadline:
            return False

        deadline.deleted = True
        deadline.updated_at = datetime.now(UTC)
        self.update_deadline(deadline, user_id)
        return True

    def list_deadlines(
        self,
        analysis_id: str,
        user_id: str,
        include_deleted: bool = False,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[Deadline]:
        """
        Lista todos los deadlines de un análisis.

        Args:
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)
            include_deleted: Si True, incluye deadlines marcados como deleted
            limit: Máximo número de resultados (None = sin límite)
            skip: Número de resultados a saltear (para paginación)

        Returns:
            Lista de deadlines

        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(self.db, analysis_id, user_id)
        return repository.list_deadlines(
            self.db, analysis_id, include_deleted=include_deleted, limit=limit, skip=skip
        )
