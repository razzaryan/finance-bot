# Build aplikasi Windows: .exe + installer.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Hasil:
#   dist\Keuangan\Keuangan.exe          aplikasi siap jalan
#   dist\installer\Keuangan-Setup-1.0.0.exe   installer
#
# Butuh: .venv dengan requirements terpasang, PyInstaller, Inno Setup 6.

param(
    [switch]$SkipInstaller,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "venv tidak ditemukan di $python. Buat dulu: python -m venv .venv"
}

Write-Host "== 1/5 tes ==" -ForegroundColor Cyan
if (-not $SkipTests) {
    & $python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "Tes gagal. Build dibatalkan." }
} else {
    Write-Host "   dilewati" -ForegroundColor DarkGray
}

Write-Host "== 2/5 ikon ==" -ForegroundColor Cyan
& $python scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Pembuatan ikon gagal." }

Write-Host "== 3/5 pyinstaller ==" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\keuangan.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller gagal." }

Write-Host "== 4/5 uji exe ==" -ForegroundColor Cyan
& $python scripts\probe_exe.py
if ($LASTEXITCODE -ne 0) { throw "Exe hasil build tidak lolos uji." }

if ($SkipInstaller) {
    Write-Host "== 5/5 installer dilewati ==" -ForegroundColor DarkGray
    exit 0
}

Write-Host "== 5/5 installer ==" -ForegroundColor Cyan
$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup tidak ditemukan. Pasang dengan: winget install JRSoftware.InnoSetup"
}

& $iscc packaging\keuangan.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup gagal." }

$installer = Get-ChildItem dist\installer\Keuangan-Setup-*.exe | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host ""
Write-Host "SELESAI" -ForegroundColor Green
Write-Host ("  Aplikasi  : {0}" -f (Join-Path $root "dist\Keuangan\Keuangan.exe"))
Write-Host ("  Installer : {0} ({1:N1} MB)" -f $installer.FullName, ($installer.Length / 1MB))
