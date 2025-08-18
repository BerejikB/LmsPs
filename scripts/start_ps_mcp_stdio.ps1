# start_ps_mcp_stdio.ps1 â€” Windows PowerShell launcher for LmsPs (stdio)
# No stdout from wrapper. Creates venv, installs (-e), verifies import, starts server.

$ErrorActionPreference = "Stop"

# ---------- logging ----------
$global:LogFile = $null
function Log([string]$m){ "[$(Get-Date -Format o)] $m" | Out-File -Append $global:LogFile -Encoding UTF8 }

function Run-Native([string]$Exe,[string]$Args){
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Exe
  $psi.Arguments = $Args
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError  = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  $out = $p.StandardOutput.ReadToEnd()
  $err = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  if ($out) { Add-Content -Path $global:LogFile -Value $out -Encoding UTF8 }
  if ($err) { Add-Content -Path $global:LogFile -Value $err -Encoding UTF8 }
  return $p.ExitCode
}

# ---------- paths ----------
$Repo  = if ($env:LMSPS_REPO) { $env:LMSPS_REPO } else { "K:\Repos\LmsPs" }
if (-not (Test-Path $Repo)) { Write-Error "REPO_NOT_FOUND:$Repo"; exit 1 }

$LogDir = if ($env:LMSPS_LOGDIR) { $env:LMSPS_LOGDIR } else {
  $local = [Environment]::GetFolderPath("LocalApplicationData")
  if ([string]::IsNullOrWhiteSpace($local)) { Write-Error "LOCALAPPDATA_NOT_FOUND"; exit 1 }
  Join-Path $local "LMstudio\LmsPs\logs"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$global:LogFile = Join-Path $LogDir "lmsps_server.log"

# ---------- python selection ----------
$PyLauncher = if ($env:LMSPS_PY -and (Test-Path $env:LMSPS_PY)) { $env:LMSPS_PY } else {
  ($c = Get-Command py.exe -ErrorAction SilentlyContinue) ? $c.Source :
  (($c = Get-Command python.exe -ErrorAction SilentlyContinue) ? $c.Source : $null)
}
if (-not $PyLauncher) { Write-Error 'PY_NOT_FOUND: install Python or add "py"/"python" to PATH'; exit 1 }
Log "Using Python launcher: $PyLauncher"

# ---------- venv ----------
$Venv  = Join-Path $Repo ".venv"
$PyExe = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $PyExe)) {
  Log "Creating venv at $Venv"
  $code = (Split-Path $PyLauncher -Leaf).ToLower().Equals("py.exe") ?
          (Run-Native $PyLauncher "-3 -m venv `"$Venv`"") :
          (Run-Native $PyLauncher "-m venv `"$Venv`"")
  if ($code -ne 0 -or -not (Test-Path $PyExe)) { Write-Error "VENV_CREATE_FAIL:$Venv"; exit 1 }
}
Log "Venv Python: $PyExe"

# ---------- install / upgrade ----------
[void](Run-Native $PyExe "-m ensurepip --upgrade")
[void](Run-Native $PyExe "-m pip install --upgrade pip")
$code = Run-Native $PyExe "-m pip install -e `"$Repo`""
if ($code -ne 0) { Write-Error "PIP_EDITABLE_INSTALL_FAIL ($code)"; exit 1 }

# ---------- import check (log-only) ----------
$code = Run-Native $PyExe "-c `"import importlib,sys; importlib.import_module('lmsps'); print('import_ok')`""
if ($code -ne 0) {
  Log "IMPORT_FAIL: retrying with --force-reinstall"
  $code = Run-Native $PyExe "-m pip install --no-deps --force-reinstall -e `"$Repo`""
  if ($code -ne 0) { Write-Error "FORCE_REINSTALL_FAIL ($code)"; exit 1 }
  $code = Run-Native $PyExe "-c `"import importlib,sys; importlib.import_module('lmsps'); print('import_ok')`""
  if ($code -ne 0) { Write-Error "IMPORT_FAIL:lmsps"; exit 1 }
}

# ---------- env & start server ----------
$env:PYTHONUTF8       = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:LMSPS_TRIM_CHARS)  { $env:LMSPS_TRIM_CHARS  = "500" }
if (-not $env:LMSPS_TIMEOUT_SEC) { $env:LMSPS_TIMEOUT_SEC = "30" }

Set-Location $Repo
Log "Starting: $PyExe -m lmsps.server --stdio"
& $PyExe -m lmsps.server --stdio 2>> $global:LogFile
exit $LASTEXITCODE
