# Backup database (PowerShell)
#
# Cara pakai manual:
#   .\scripts\backup.ps1
#
# Daftarkan ke Task Scheduler Windows (harian 03:00):
#   schtasks /create /tn "FinanceBotBackup" /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\ke\finance-bot\scripts\backup.ps1" /sc daily /st 03:00

param(
    [string]$DbPath = (Join-Path $PSScriptRoot "..\data\finance.db"),
    [string]$BackupDir = (Join-Path $PSScriptRoot "..\data\backups"),
    [int]$Keep = 7
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DbPath)) {
    Write-Error "Database tidak ditemukan: $DbPath"
    exit 1
}

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupDir "finance-$stamp.db"

# VACUUM INTO butuh sqlite3.exe. Kalau tidak ada, fallback ke copy biasa
# (aman selama bot berhenti; dengan WAL, copy saat bot jalan bisa tidak konsisten).
$sqlite = Get-Command sqlite3 -ErrorAction SilentlyContinue
if ($sqlite) {
    $db = (Resolve-Path $DbPath).Path
    $out = (Join-Path (Resolve-Path $BackupDir).Path "finance-$stamp.db")
    & $sqlite.Source $db "VACUUM INTO '$out'"
    if ($LASTEXITCODE -ne 0) { throw "VACUUM INTO gagal" }
} else {
    Write-Warning "sqlite3.exe tidak ditemukan. Memakai copy biasa - hentikan bot dulu."
    Copy-Item $DbPath $target -Force
}

Write-Host "Backup dibuat: $target"

# Pangkas backup lama
$old = Get-ChildItem -Path $BackupDir -Filter "finance-*.db" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep

foreach ($f in $old) {
    Remove-Item $f.FullName -Force
    Write-Host "Dihapus: $($f.Name)"
}
