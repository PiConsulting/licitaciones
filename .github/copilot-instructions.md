# GitHub Copilot — Instrucciones de Proyecto

## Workflow Git (OBLIGATORIO antes de tocar código)

### Ramas protegidas
- `main` — producción. Solo recibe merges desde `develop` vía PR.
- `develop` — integración. Solo recibe merges desde ramas de feature/fix vía PR.

### Antes de modificar cualquier archivo de código
1. Verificar rama actual: `git branch --show-current`
2. Si estás en `main` o `develop`, **crear una rama nueva desde `develop`**:
   ```
   git checkout develop
   git pull origin develop
   git checkout -b <tipo>/<descripcion-corta>
   ```
3. Nunca commitear directamente a `main` ni a `develop`.

### Nomenclatura de ramas
```
feat/<descripcion-corta>      → nueva funcionalidad
fix/<descripcion-corta>       → corrección de bug
chore/<descripcion-corta>     → tareas de mantenimiento (deps, config, docs)
refactor/<descripcion-corta>  → refactorización sin cambio funcional
test/<descripcion-corta>      → solo tests
```
Ejemplos: `feat/pipeline-ia-extraccion`, `fix/auth-token-expiry`, `chore/update-deps`

---

## Estructura de commits (OBLIGATORIO — siempre usar este formato exacto)

Cada `git commit` que hagas debe seguir esta estructura sin excepción:

```
<tipo>(<scope>): <descripcion imperativa en minúsculas, máx 72 chars>

[cuerpo: qué cambió y por qué — omitir si el título es suficiente]

[footer: Closes #N  /  BREAKING CHANGE: descripción]
```

**Reglas:**
- La primera línea NUNCA supera 72 caracteres.
- La descripción es imperativa y en minúsculas: `agregar`, `corregir`, `eliminar` — no `agregado`, `se agregó`.
- El scope es obligatorio cuando el cambio es específico de un módulo.
- Cuerpo y footer son opcionales; si los usás, dejar una línea en blanco entre secciones.

### Tipos válidos
| Tipo | Cuándo usarlo |
|------|---------------|
| `feat` | Nueva funcionalidad visible para el usuario |
| `fix` | Corrección de bug |
| `refactor` | Cambio de código sin cambio funcional |
| `test` | Agregar o corregir tests |
| `chore` | Mantenimiento: deps, scripts, config, CI |
| `docs` | Solo documentación |
| `style` | Formato, whitespace, sin cambio de lógica |
| `perf` | Mejora de rendimiento |

### Scopes válidos
`frontend` · `backend` · `auth` · `analysis` · `documents` · `storage` · `db` · `ci` · `agents`

### Ejemplos correctos
```
feat(analysis): agregar endpoint para listar análisis paginados
```
```
fix(auth): corregir expiración de token cuando timezone es UTC-3
```
```
chore(ci): agregar step de lint en GitHub Actions
```
```
test(documents): cubrir caso de archivo duplicado por sha256

El hash sha256 no se validaba cuando el mismo archivo se subía
desde dos análisis distintos en la misma sesión.
```

---

## Cómo crear un PR

### Destino siempre es `develop` (nunca directamente a `main`)

### Título del PR
Mismo formato que el commit principal:
```
feat(analysis): agregar endpoint para listar análisis paginados
```

### Usar el template `.github/pull_request_template.md` — se carga automáticamente.

---

## Contexto del proyecto
Leer `project-context.md` en la raíz antes de cualquier acción de código.
