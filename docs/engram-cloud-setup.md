# Engram Cloud — Setup para el equipo

Engram provee memoria persistente a los agentes de IA que trabajan sobre este repositorio.
Cada agente (VS Code Copilot, BMAD, etc.) escribe y lee memorias vía MCP. Engram Cloud las sincroniza entre todos los desarrolladores.

## Arquitectura

```
VS Code Copilot (agente)
      ↓ MCP stdio (automático al abrir VS Code)
engram mcp --project=licitaciones-pi --tools=agent
      ↓ local SQLite (~/.engram/engram.db)
      ↕ autosync (en segundo plano)
Engram Cloud (Docker: ghcr.io/gentleman-programming/engram)
      ↓
Postgres (compartido por el equipo)
```

La base SQLite local es siempre la fuente de verdad. Engram Cloud es replicación opcional.

---

## 1. Prerrequisito: instalar el binario Engram

### Windows (recomendado)
Descargá el binario desde [releases](https://github.com/Gentleman-Programming/engram/releases) y ubicalo en algún directorio de tu `PATH`.

O vía Scoop:
```powershell
scoop bucket add gentleman-programming https://github.com/Gentleman-Programming/scoop-bucket
scoop install engram
```

### macOS / Linux
```bash
brew install gentleman-programming/tap/engram
```

Verificá la instalación:
```bash
engram version
```

---

## 2. Registrar el MCP en VS Code (ya hecho por el repo)

El archivo [`.vscode/mcp.json`](../.vscode/mcp.json) ya está committeado y le dice a VS Code cómo iniciar el servidor MCP de Engram con el proyecto correcto. Al abrir el workspace, VS Code levanta `engram mcp --project=licitaciones-pi` automáticamente.

> No necesitás configurar nada manualmente en VS Code. Solo instalar el binario.

Si querés verificar que el MCP está activo: en VS Code abrí Command Palette (`Ctrl+Shift+P`) → `MCP: List Servers`.

---

## 3. Configurar Engram Cloud (para sync de equipo)

### 3a. Levantar el servidor Cloud (quién lo deploya — una sola vez)

El responsable de infraestructura del equipo debe:

```bash
# 1. Copiar el template de configuración
cp .env.cloud.example .env.cloud

# 2. Editar .env.cloud con valores reales (ver tabla abajo)
# NUNCA commitear .env.cloud

# 3. Levantar el stack
docker compose -f docker-compose.cloud.yml up -d

# 4. Verificar que el servidor responde
curl http://localhost:18080/health
```

#### Variables requeridas en `.env.cloud`

| Variable | Descripción |
|---|---|
| `ENGRAM_POSTGRES_USER` | Usuario de Postgres |
| `ENGRAM_POSTGRES_PASSWORD` | Contraseña de Postgres (fuerte) |
| `ENGRAM_POSTGRES_DB` | Nombre de la base de datos |
| `ENGRAM_DATABASE_URL` | URL completa de conexión a Postgres |
| `ENGRAM_CLOUD_TOKEN` | Token bearer que usan los clientes para sincronizar (mínimo 32 chars) |
| `ENGRAM_CLOUD_ADMIN` | Token separado para el dashboard de administración |
| `ENGRAM_JWT_SECRET` | Secret para JWT (mínimo 32 bytes, distinto de los tokens) |
| `ENGRAM_CLOUD_ALLOWED_PROJECTS` | Lista de proyectos que pueden sincronizar (ej: `licitaciones-pi`) |

#### Generar tokens seguros

```bash
# PowerShell
[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))

# macOS / Linux
openssl rand -base64 32
```

### 3b. Configurar cada desarrollador para usar el Cloud

Cada miembro del equipo debe agregar estas variables a su **entorno de sistema o perfil de shell** (no en ningún `.env` del proyecto):

```bash
# Bash / Zsh — agregar a ~/.bashrc o ~/.zshrc
export ENGRAM_CLOUD_SERVER=https://tu-servidor-engram:18080
export ENGRAM_CLOUD_TOKEN=el-token-bearer-del-equipo
export ENGRAM_CLOUD_AUTOSYNC=1
```

```powershell
# PowerShell — agregar a $PROFILE o configurar como variables de sistema
$env:ENGRAM_CLOUD_SERVER = "https://tu-servidor-engram:18080"
$env:ENGRAM_CLOUD_TOKEN  = "el-token-bearer-del-equipo"
$env:ENGRAM_CLOUD_AUTOSYNC = "1"
```

> En Windows, la forma más duradera es configurarlas como variables de entorno del sistema en: **Settings → System → About → Advanced system settings → Environment Variables**.

VS Code hereda el entorno del proceso que lo lanzó. Si abrís VS Code desde una terminal donde esas variables ya están activas, el MCP las tomará automáticamente.

### 3c. Enrollar el proyecto y hacer el primer sync

```bash
# Una sola vez por desarrollador, luego es automático
engram cloud config --server https://tu-servidor-engram:18080
engram cloud enroll licitaciones-pi
engram sync --cloud --project licitaciones-pi
```

---

## 4. Flujo de trabajo diario

Una vez configurado, el flujo es transparente:

1. **Abrís VS Code** → el agente MCP de Engram se levanta automáticamente
2. **El agente trabaja** → cada decisión, bugfix o descubrimiento importante se guarda con `mem_save`
3. **Engram Cloud sincroniza** en segundo plano (`ENGRAM_CLOUD_AUTOSYNC=1`)
4. **Otro desarrollador abre VS Code** → su agente lee las memorias del equipo vía `mem_search` o `mem_context`

### Convenciones del equipo

| Regla | Detalle |
|---|---|
| Idioma de `scope: project` | **Español** (el proyecto trabaja en español) |
| Idioma de `scope: personal` | Libre |
| Tipo para decisiones de arquitectura | `type: architecture` |
| Tipo para bugfixes | `type: bugfix` |
| Tipo para convenciones de código | `type: pattern` |

---

## 5. Comandos útiles

```bash
# Ver memorias del proyecto
engram tui

# Buscar en la memoria
engram search "autenticación JWT"

# Ver contexto reciente de la sesión
engram context licitaciones-pi

# Estado del sync con el Cloud
engram sync --cloud --status --project licitaciones-pi

# Diagnóstico de problemas
engram doctor

# Diagnóstico del Cloud
engram cloud status
```

---

## 6. Ventajas de Engram Cloud sobre memoria solo local

| | Solo local | Con Engram Cloud |
|---|---|---|
| Decisiones de arquitectura | Solo en tu máquina | Disponibles para todo el equipo |
| Onboarding de nuevos devs | El agente empieza "en blanco" | El agente hereda el contexto acumulado |
| Continuidad entre sesiones | Persiste por máquina | Persiste por proyecto, cross-máquina |
| Recuperación tras compactación | Solo si el agente pregunta | Automática: `mem_context` recupera el estado |
| Conflictos de decisiones | Invisibles | Surfaceados automáticamente por `mem_save` |

---

## Referencias

- [Engram README](https://github.com/Gentleman-Programming/engram)
- [Agent Setup](https://github.com/Gentleman-Programming/engram/blob/main/docs/AGENT-SETUP.md)
- [Engram Cloud Quickstart](https://github.com/Gentleman-Programming/engram/blob/main/docs/engram-cloud/quickstart.md)
- [Team Usage Guide](https://github.com/Gentleman-Programming/engram/blob/main/docs/TEAM-USAGE.md)
