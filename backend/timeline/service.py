"""
Servicios de persistencia CRUD para Timeline en Cosmos DB.

Operaciones CRUD para eventos y deadlines siguiendo el patrón
del proyecto: partition_key = analysis_id.

SEGURIDAD: Todos los métodos validan que el user_id tenga ownership
del analysis_id antes de permitir operaciones.
"""
from datetime import datetime, UTC
from typing import Optional

from azure.cosmos import ContainerProxy, exceptions as cosmos_exceptions

from shared.cosmos_container import get_cosmos_container
from timeline.auth import validate_analysis_access
from timeline.models import Event, Deadline


class TimelineService:
    """Servicio de persistencia para eventos y deadlines en Cosmos DB."""
    
    def __init__(self, container: Optional[ContainerProxy] = None):
        """
        Inicializa el servicio con un contenedor Cosmos.
        
        Args:
            container: Contenedor Cosmos. Si es None, usa get_cosmos_container().
        """
        self.container = container or get_cosmos_container()
    
    # ==================== EVENTS ====================
    
    def create_event(self, event: Event, user_id: str) -> Event:
        """
        Crea un nuevo evento en Cosmos DB.
        
        Args:
            event: Modelo Event a persistir
            user_id: ID del usuario actual (para validación de ownership)
            
        Returns:
            Event creado con timestamps actualizados
            
        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(event.analysis_id, user_id)
        event_dict = event.model_dump(mode="json")
        self.container.create_item(body=event_dict)
        return event
    
    def get_event(self, event_id: str, analysis_id: str, user_id: str) -> Optional[Event]:
        """
        Obtiene un evento por ID.
        
        Args:
            event_id: ID del evento (sin prefijo "event::")
            analysis_id: ID del análisis (partition key)
            user_id: ID del usuario actual (para validación de ownership)
            
        Returns:
            Event si existe, None si no se encuentra
            
        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(analysis_id, user_id)
        try:
            item = self.container.read_item(
                item=f"event::{event_id}",
                partition_key=analysis_id
            )
            return Event(**item)
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None
    
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
            CosmosResourceNotFoundError: Si el evento no existe
        """
        validate_analysis_access(event.analysis_id, user_id)
        event.updated_at = datetime.now(UTC)
        event_dict = event.model_dump(mode="json")
        self.container.replace_item(item=event.id, body=event_dict)
        return event
    
    def delete_event(self, event_id: str, analysis_id: str, user_id: str) -> bool:
        """
        Soft delete de un evento (marca deleted=True).
        
        Args:
            event_id: ID del evento (sin prefijo)
            analysis_id: ID del análisis (partition key)
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
        limit: Optional[int] = None,
        skip: int = 0
    ) -> list[Event]:
        """
        Lista todos los eventos de un análisis.
        
        Args:
            analysis_id: ID del análisis
            user_id: ID del usuario actual (para validación de ownership)
            include_deleted: Si True, incluye eventos marcados como deleted
            limit: Máximo número de resultados (None = sin límite)
            skip: Número de resultados a saltear (para paginación)
            
        Returns:
            Lista de eventos
            
        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(analysis_id, user_id)
        query = "SELECT * FROM c WHERE c.type = 'event' AND c.partition_key = @analysis_id"
        if not include_deleted:
            query += " AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
        
        # Agregar ordenamiento por created_at para paginación consistente
        query += " ORDER BY c.created_at DESC"
        
        # Agregar paginación si se especificó
        if skip > 0:
            query += f" OFFSET {skip}"
        if limit is not None:
            query += f" LIMIT {limit}"
        
        parameters = [{"name": "@analysis_id", "value": analysis_id}]
        
        items = list(self.container.query_items(
            query=query,
            parameters=parameters,
            partition_key=analysis_id
        ))
        
        return [Event(**item) for item in items]
    
    # ==================== DEADLINES ====================
    
    def create_deadline(self, deadline: Deadline, user_id: str) -> Deadline:
        """
        Crea un nuevo deadline en Cosmos DB.
        
        Args:
            deadline: Modelo Deadline a persistir
            user_id: ID del usuario actual (para validación de ownership)
            
        Returns:
            Deadline creado
            
        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(deadline.analysis_id, user_id)
        deadline_dict = deadline.model_dump(mode="json")
        self.container.create_item(body=deadline_dict)
        return deadline
    
    def get_deadline(self, deadline_id: str, analysis_id: str, user_id: str) -> Optional[Deadline]:
        """
        Obtiene un deadline por ID.
        
        Args:
            deadline_id: ID del deadline (sin prefijo "deadline::")
            analysis_id: ID del análisis (partition key)
            user_id: ID del usuario actual (para validación de ownership)
            
        Returns:
            Deadline si existe, None si no se encuentra
            
        Raises:
            HTTPException: 404 si análisis no existe, 403 si no es owner
        """
        validate_analysis_access(analysis_id, user_id)
        try:
            item = self.container.read_item(
                item=f"deadline::{deadline_id}",
                partition_key=analysis_id
            )
            return Deadline(**item)
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None
    
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
        validate_analysis_access(deadline.analysis_id, user_id)
        deadline.updated_at = datetime.now(UTC)
        deadline_dict = deadline.model_dump(mode="json")
        self.container.replace_item(item=deadline.id, body=deadline_dict)
        return deadline
    
    def delete_deadline(self, deadline_id: str, analysis_id: str, user_id: str) -> bool:
        """
        Soft delete de un deadline.
        
        Args:
            deadline_id: ID del deadline (sin prefijo)
            analysis_id: ID del análisis (partition key)
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
        limit: Optional[int] = None,
        skip: int = 0
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
        validate_analysis_access(analysis_id, user_id)
        query = "SELECT * FROM c WHERE c.type = 'deadline' AND c.partition_key = @analysis_id"
        if not include_deleted:
            query += " AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
        
        # Agregar ordenamiento por created_at para paginación consistente
        query += " ORDER BY c.created_at DESC"
        
        # Agregar paginación si se especificó
        if skip > 0:
            query += f" OFFSET {skip}"
        if limit is not None:
            query += f" LIMIT {limit}"
        
        parameters = [{"name": "@analysis_id", "value": analysis_id}]
        
        items = list(self.container.query_items(
            query=query,
            parameters=parameters,
            partition_key=analysis_id
        ))
        
        return [Deadline(**item) for item in items]
