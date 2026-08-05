param(
    [string[]]$Paths = @(
        "./local_blob_storage",
        "./backend/local_blob_storage"
    )
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

foreach ($PathItem in $Paths) {
    $resolvedPath = Join-Path (Get-Location) $PathItem
    if (-not (Test-Path $resolvedPath)) {
        Write-Host "[clean-local-storage] No existe: $resolvedPath"
        continue
    }

    Write-Host "[clean-local-storage] Limpiando: $resolvedPath"
    Get-ChildItem -Path $resolvedPath -Force | Remove-Item -Recurse -Force
}

Write-Host "[clean-local-storage] Limpieza completada."
