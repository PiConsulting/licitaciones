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

## Estructura de commits (Conventional Commits)

```
<tipo>(<scope opcional>): <descripcion imperativa en minúsculas>

[cuerpo opcional — qué y por qué, no el cómo]

[footer opcional — cierra issues, breaking changes]
```

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

### Scopes sugeridos
`frontend`, `backend`, `auth`, `analysis`, `documents`, `storage`, `db`, `ci`, `agents`

### Ejemplos
```
feat(analysis): agregar endpoint para listar análisis paginados

fix(auth): corregir expiración de token cuando timezone es UTC-3

chore(ci): agregar step de lint en GitHub Actions

test(documents): cubrir caso de archivo duplicado por sha256
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
