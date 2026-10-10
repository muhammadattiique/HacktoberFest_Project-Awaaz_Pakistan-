<#
Phase 0 baseline: frontend build size, Lighthouse, and runtime perf orchestrator.

Reproducible driver for the frontend baseline. It:
  1. Builds the production bundle (vite build) and records per-chunk sizes.
  2. Serves the build with `vite preview` (background) on a free port.
  3. Runs Lighthouse (mobile + desktop) for home (/) and dashboard (/admin)
     via `npx --yes lighthouse` using headless Chrome. Reports are written to
     awaaz_pakistan/ui-baseline/lighthouse/ as HTML + JSON. Lighthouse is run
     ephemerally and is NOT added to package.json.
  4. Runs ui-baseline/scripts/perf.mjs (Playwright/CDP, 4x CPU throttle, mobile
     viewport) for load time + 3D FPS.
  5. Writes a summary to awaaz_backend/bench/results/baseline/frontend.json.
  6. Stops the preview server and DELETES dist/ (never committed).

Run from the awaaz_pakistan directory:
    pwsh -File .\ui-baseline\scripts\frontend_bench.ps1

Prereqs: node/npm, installed Chrome and Edge, and Playwright installed
ephemerally at $env:TEMP\awaaz_pw (see ui-baseline/INDEX.md).
#>
[CmdletBinding()]
param(
  [string]$Front,
  [string]$ChromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Front) { $Front = (Resolve-Path (Join-Path $scriptDir '..\..')).Path }
$results = [ordered]@{}
$results.generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
$lhDir = Join-Path $Front 'ui-baseline\lighthouse'
$outJson = Resolve-Path (Join-Path $Front '..\awaaz_backend\bench\results\baseline')
$outJson = Join-Path $outJson 'frontend.json'
New-Item -ItemType Directory -Force -Path $lhDir | Out-Null

Push-Location $Front
$preview = $null
try {
  # 1. Build
  Write-Host '== vite build =='
  $buildLog = npm run build 2>&1 | Out-String
  Write-Host $buildLog
  $distAssets = Join-Path $Front 'dist\assets'
  $chunks = @()
  $totalBytes = 0
  if (Test-Path $distAssets) {
    Get-ChildItem $distAssets -File | ForEach-Object {
      $chunks += [ordered]@{ file = $_.Name; bytes = $_.Length; kib = [math]::Round($_.Length / 1024, 2) }
      $totalBytes += $_.Length
    }
  }
  $indexHtml = Join-Path $Front 'dist\index.html'
  $indexBytes = $null
  if (Test-Path $indexHtml) { $indexBytes = (Get-Item $indexHtml).Length }
  $results.build = [ordered]@{
    tool          = 'vite build (production)'
    index_html_bytes = $indexBytes
    assets        = $chunks
    total_assets_bytes = $totalBytes
    note          = 'gzip sizes are in the raw build log; byte sizes here are uncompressed on-disk.'
    raw_build_log = $buildLog.Trim()
  }

  # 2. Static server for the production build on a fixed port.
  # A plain long-lived Node static server is used instead of `vite preview`
  # because the npm -> vite child launched under Start-Process died after the
  # first headless-Chrome run (CHROME_INTERSTITIAL_ERROR). It serves the same
  # production dist/ with an SPA fallback for /admin.
  $port = 4173
  Write-Host "== static server on $port =="
  $staticServer = Join-Path $scriptDir 'static_server.mjs'
  $distDir = Join-Path $Front 'dist'
  $preview = Start-Process -FilePath 'node' -ArgumentList @($staticServer, $distDir, "$port") -PassThru -WindowStyle Hidden
  $base = "http://127.0.0.1:$port"
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$base/" | Out-Null; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $ready) { throw 'static server did not become ready' }

  # 3. Lighthouse (mobile + desktop) for home and dashboard
  $results.lighthouse = [ordered]@{}
  $targets = @(
    @{ name = 'home';      url = "$base/" },
    @{ name = 'dashboard'; url = "$base/admin" }
  )
  $forms = @('mobile','desktop')
  foreach ($t in $targets) {
    foreach ($form in $forms) {
      $tag = "$($t.name)_$form"
      $jsonPath = Join-Path $lhDir "$tag.report.json"
      $htmlPath = Join-Path $lhDir "$tag.report.html"
      Write-Host "== lighthouse $tag =="

      # Re-confirm the preview server is still serving before each run. Running
      # Lighthouse back-to-back can otherwise hit a transient window where the
      # server has not accepted a new connection yet, producing a
      # CHROME_INTERSTITIAL_ERROR (page redirected to chrome-error://).
      $srvOk = $false
      for ($r = 0; $r -lt 20; $r++) {
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $t.url | Out-Null; $srvOk = $true; break } catch { Start-Sleep -Milliseconds 500 }
      }
      if (-not $srvOk) { $results.lighthouse[$tag] = [ordered]@{ status = "NOT MEASURED: preview server not responding at $($t.url)" }; continue }

      # Isolate each run in its own Chrome profile dir so interstitial / error
      # state from a previous run cannot bleed into the next.
      $udd = Join-Path ([System.IO.Path]::GetTempPath()) ("awaaz_lh_" + [guid]::NewGuid().ToString('N'))
      $lhArgs = @(
        $t.url,
        '--output=json', '--output=html',
        "--output-path=$(Join-Path $lhDir $tag)",
        '--quiet',
        "--chrome-flags=--headless=new --no-sandbox --disable-gpu --user-data-dir=`"$udd`"",
        '--max-wait-for-load=45000',
        '--only-categories=performance,accessibility'
      )
      if ($form -eq 'desktop') { $lhArgs += '--preset=desktop' }
      try {
        & npx --yes lighthouse @lhArgs 2>&1 | Out-Null
        # lighthouse writes <path>.report.json / <path>.report.html
        $perfScore = $null; $a11yScore = $null; $metrics = @{}
        if (Test-Path $jsonPath) {
          $lh = Get-Content $jsonPath -Raw | ConvertFrom-Json
          $perfScore = [math]::Round(($lh.categories.performance.score) * 100)
          $a11yScore = [math]::Round(($lh.categories.accessibility.score) * 100)
          $metrics = [ordered]@{
            first_contentful_paint = $lh.audits.'first-contentful-paint'.displayValue
            largest_contentful_paint = $lh.audits.'largest-contentful-paint'.displayValue
            total_blocking_time = $lh.audits.'total-blocking-time'.displayValue
            cumulative_layout_shift = $lh.audits.'cumulative-layout-shift'.displayValue
            speed_index = $lh.audits.'speed-index'.displayValue
          }
        }
        $results.lighthouse[$tag] = [ordered]@{
          url = $t.url; form_factor = $form
          performance = $perfScore; accessibility = $a11yScore
          metrics = $metrics
          html_report = (Split-Path $htmlPath -Leaf)
          json_report = (Split-Path $jsonPath -Leaf)
        }
      } catch {
        $results.lighthouse[$tag] = [ordered]@{ status = "NOT MEASURED: $($_.Exception.Message)" }
      } finally {
        if (Test-Path $udd) { Remove-Item $udd -Recurse -Force -ErrorAction SilentlyContinue }
      }
    }
  }

  # 4. Runtime perf (load + FPS) via Playwright/CDP
  Write-Host '== perf.mjs (load + 3D FPS) =='
  $env:AWAAZ_BASE_URL = $base
  # Resolve the ephemeral Playwright install explicitly so the node child does
  # not depend on it being inherited from the caller's shell.
  if (-not $env:PLAYWRIGHT_MODULE) {
    $env:PLAYWRIGHT_MODULE = Join-Path ([System.IO.Path]::GetTempPath()) 'awaaz_pw\node_modules\playwright'
  }
  try {
    $perfJson = node (Join-Path $scriptDir 'perf.mjs') 2>&1 | Out-String
    $results.runtime = ($perfJson | ConvertFrom-Json)
  } catch {
    $results.runtime = [ordered]@{ status = "NOT MEASURED: $($_.Exception.Message)"; raw = $perfJson.Trim() }
  }
}
finally {
  if ($preview -and -not $preview.HasExited) { Stop-Process -Id $preview.Id -Force -ErrorAction SilentlyContinue }
  # Delete the build output; it must never be committed.
  $dist = Join-Path $Front 'dist'
  if (Test-Path $dist) { Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue }
  Pop-Location
}

# Write UTF-8 without BOM so JSON parsers (python/jq) read it cleanly.
$json = $results | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($outJson, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Wrote $outJson"

