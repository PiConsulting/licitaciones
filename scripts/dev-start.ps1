param(
    [switch]$InstallDeps,
    [switch]$CleanLocalStorage,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$CleanScript = Join-Path $RepoRoot "scripts\clean-local-storage.ps1"

if (-not (Test-Path $PythonExe)) {
    throw "No se encontró Python en .venv. Creá el entorno virtual antes de ejecutar este script."
}

Write-Host "[dev-start] Repo: $RepoRoot"
Write-Host "[dev-start] Python: $PythonExe"

if ($InstallDeps) {
    Write-Host "[dev-start] Instalando dependencias backend..."
    Push-Location $BackendDir
    & $PythonExe -m pip install -e .
    Pop-Location

    Write-Host "[dev-start] Instalando dependencias frontend..."
    Push-Location $FrontendDir
    npm install
    Pop-Location
}

if ($CleanLocalStorage) {
    Write-Host "[dev-start] Limpiando storage local..."
    & powershell -ExecutionPolicy Bypass -File $CleanScript
}

if ($DryRun) {
    Write-Host "[dev-start] DryRun activo. No se ejecutaran migraciones ni se abriran terminales."
    Write-Host "[dev-start] Comando backend: $PythonExe -m uvicorn main:app --reload --app-dir backend"
    Write-Host "[dev-start] Comando frontend: npm run dev (en $FrontendDir)"
    exit 0
}

Write-Host "[dev-start] Ejecutando migraciones Alembic..."
Push-Location $BackendDir
$upgradeArgs = @("-m", "alembic", "upgrade", "head")
& $PythonExe @upgradeArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[dev-start] alembic upgrade head fallo. Intentando reconciliar estado parcial de migraciones..."

    # Caso comun: tabla users existente pero alembic_version ausente o desfasada.
    & $PythonExe -m alembic stamp 20260803_0001
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo aplicar alembic stamp 20260803_0001"
    }

    & $PythonExe @upgradeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo ejecutar alembic upgrade head despues de reconciliar estado"
    }
}

Write-Host "[dev-start] Ejecutando seed de usuario de prueba..."
& $PythonExe seed.py
Pop-Location

$BackendCommand = "Set-Location '$RepoRoot'; & '$PythonExe' -m uvicorn main:app --reload --app-dir backend"
$FrontendCommand = "Set-Location '$FrontendDir'; npm run dev"

Write-Host "[dev-start] Levantando backend en nueva terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $BackendCommand
) | Out-Null

Write-Host "[dev-start] Levantando frontend en nueva terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $FrontendCommand
) | Out-Null

Write-Host "[dev-start] Listo."
Write-Host "  Backend:  http://localhost:8000"
Write-Host "  Frontend: http://localhost:5173"
