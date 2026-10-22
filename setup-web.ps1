$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.local/model-env/Scripts/python.exe')) {
    python -m venv .local/model-env
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10-3.12 is required.' }
}
$inkPython = Join-Path $PSScriptRoot '.local/model-env/Scripts/python.exe'
& $inkPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize pip in the project environment.' }
& $inkPython -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
& $inkPython -m pip install -r web/requirements.txt -r web/runtime/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $inkPython scripts/setup_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed; rerun to resume.' }
Write-Output 'Ready. Double-click Start Inkself.cmd.'
