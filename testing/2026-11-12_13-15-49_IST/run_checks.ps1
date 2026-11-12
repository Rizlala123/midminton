param([switch]$ConfirmTargetMachine)
$ErrorActionPreference = 'Stop'
if (-not $ConfirmTargetMachine) {
    throw 'Target PC only. Read requirements.md, then pass -ConfirmTargetMachine explicitly.'
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Create the target-PC .venv first.' }
if (-not (Test-Path -LiteralPath 'src-tauri\icons\icon.ico')) { throw 'Run tools/prepare_icons.py on this PC first.' }
if (-not (Test-Path -LiteralPath 'node_modules')) { throw 'Run npm install on this PC first.' }
& $pythonExecutable -m pytest python/tests -q
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
& npm.cmd run check
if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
& cargo check --manifest-path src-tauri/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw 'Rust check failed.' }
Write-Host 'Automated checks passed on this PC. App, model, export and installer acceptance remain separate.'
