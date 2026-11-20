param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
try {
    $url = 'http://127.0.0.1:8767'
    $page = Join-Path $PSScriptRoot 'web/out/index.html'
    if (!(Test-Path -LiteralPath $page)) { throw 'First build the web folder (npm run build).' }
    $deps = Join-Path $env:LOCALAPPDATA 'NexusLabelLab/python-deps'
    $venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $venvPython) {
        $python = $venvPython
    } else {
        $python = (Get-Command python -CommandType Application | Select-Object -First 1).Source
        if (Test-Path -LiteralPath $deps) { $env:PYTHONPATH = "$deps;$env:PYTHONPATH" }
    }
    $service = $null
    try { $service = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 1 } catch {}
    if ($null -ne $service -and $service.service -ne 'nexus-local-lab') { throw 'Port 8767 is occupied by another service.' }
    if ($null -ne $service -and $service.projectRoot -and $service.projectRoot -ne $PSScriptRoot) {
        throw "Another dashboard copy is using port 8767: $($service.projectRoot)"
    }
    if ($null -eq $service) {
        $logs = Join-Path $env:LOCALAPPDATA 'NexusLabelLab'
        New-Item -ItemType Directory -Force -Path $logs | Out-Null
        $p = Start-Process -FilePath $python -ArgumentList '-X','utf8','-m','uvicorn','lab_api:app','--host','127.0.0.1','--port','8767' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'lab-out.log') -RedirectStandardError (Join-Path $logs 'lab-error.log')
        for ($i=0; $i -lt 60 -and $null -eq $service; $i++) {
            $p.Refresh()
            if ($p.HasExited) { throw "The lab did not start. Logs: $logs" }
            Start-Sleep -Milliseconds 250
            try { $service = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 1 } catch {}
        }
    }
    if ($service.service -ne 'nexus-local-lab' -or !$service.pageBuilt) { throw 'The local lab did not report readiness.' }
    if ($NoBrowser) { Write-Output $url } else { Start-Process $url }
} catch { Write-Host $_.Exception.Message; exit 1 }
