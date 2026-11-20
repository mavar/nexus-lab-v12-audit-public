param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $version = & python -c "import sys; print('.'.join(map(str,sys.version_info[:2])))"
    if ($LASTEXITCODE -or $version.Trim() -ne '3.12') { throw 'Install Python 3.12 and add it to PATH.' }
    $nodeMajor = & node -p "process.versions.node.split('.')[0]"
    if ($LASTEXITCODE -or [int]$nodeMajor -lt 24) { throw 'Install Node.js 24 LTS and add it to PATH.' }
    & python -m venv .venv
    if ($LASTEXITCODE) { throw 'Cannot prepare .venv.' }
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    & $python -m pip install -r requirements.txt -r requirements-api.txt -c requirements-lock.txt
    if ($LASTEXITCODE) { throw 'Python dependencies failed.' }
    if ($Demo) {
        & $python -X utf8 prepare_demo.py
        if ($LASTEXITCODE) { throw 'Demo data preparation failed.' }
    }
    & $python -X utf8 -c "import json; from pathlib import Path; from lab_api import app; Path('web/openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2),encoding='utf-8')"
    if ($LASTEXITCODE) { throw 'OpenAPI generation failed.' }
    Push-Location web
    try {
        & npm.cmd ci --prefer-offline --no-fund --maxsockets=4 --fetch-retries=2 --fetch-timeout=120000
        if ($LASTEXITCODE) {
            Write-Output 'Retrying the locked Next.js archive in small verified parts.'
            & $python (Join-Path $PSScriptRoot 'fetch_next.py')
            if ($LASTEXITCODE) { throw 'Cannot prepare the official Next.js archive.' }
            & npm.cmd ci --offline --no-audit --no-fund
            if ($LASTEXITCODE) { throw 'Web dependencies failed. Restore network access and retry setup.' }
        }
        & npx.cmd --no-install openapi-typescript openapi.json -o src/lib/api.d.ts
        if ($LASTEXITCODE) { throw 'API type generation failed.' }
        $env:NEXT_TELEMETRY_DISABLED = '1'
        & npm.cmd run build
        if ($LASTEXITCODE) { throw 'Web build failed.' }
    } finally { Pop-Location }
    & $python -X utf8 -m unittest test_learning test_timed
    if ($LASTEXITCODE) { throw 'Python checks failed.' }
    & node test_engine.js
    if ($LASTEXITCODE) { throw 'Label engine checks failed.' }
    Write-Output 'Setup complete. Start START_LAB.bat.'
} catch {
    Write-Host $_.Exception.Message
    exit 1
} finally { Pop-Location }
