# Static file server for CamWalkingGame (no Python required).
# Photos posted to /api/photo are saved under the demo root pics\ folder.
# Prefer the root entry: AutorunWin.bat (double-click).
# Direct run: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\AutorunWin.ps1
param(
  [string]$Root = "",
  [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
if (-not $Root) {
  # scripts\ → repo root → app\
  $Root = Join-Path (Split-Path -Parent $PSScriptRoot) "app"
}
$Root = (Resolve-Path -LiteralPath $Root).Path
if (-not (Test-Path -LiteralPath (Join-Path $Root "index.html"))) {
  Write-Host "[ERROR] index.html not found under: $Root"
  Read-Host "Press Enter to exit"
  exit 1
}
$handModel = Join-Path $Root "vendor\mediapipe\models\hand_landmarker.task"
$poseModel = Join-Path $Root "vendor\mediapipe\models\pose_landmarker_lite.task"
if (-not (Test-Path -LiteralPath $handModel)) {
  Write-Host "[WARN] Missing hand_landmarker.task. Finger tracking will not load."
}
if (-not (Test-Path -LiteralPath $poseModel)) {
  Write-Host "[WARN] Missing pose_landmarker_lite.task. Elbow and knee tracking will not load."
}

function Test-PortFree([int]$Candidate) {
  $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Candidate)
  try {
    $probe.Start()
    return $true
  } catch {
    return $false
  } finally {
    try { $probe.Stop() } catch { }
  }
}

$preferred = @($Port, 8080, 8081, 8082, 8765) | Select-Object -Unique
foreach ($candidate in $preferred) {
  if (Test-PortFree $candidate) {
    $Port = $candidate
    break
  }
}

function Open-DemoBrowser([string]$Url) {
  $candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($exe in $candidates) {
    if ($exe -and (Test-Path -LiteralPath $exe)) {
      Start-Process -FilePath $exe -ArgumentList $Url
      return
    }
  }
  Start-Process $Url
}

$prefix = "http://127.0.0.1:$Port/"
$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add($prefix)
try {
  $listener.Start()
} catch {
  Write-Host "[ERROR] Cannot listen on $prefix"
  Write-Host $_.Exception.Message
  Write-Host "Is port $Port already in use?"
  Read-Host "Press Enter to exit"
  exit 1
}

$picsDir = Join-Path (Split-Path -Parent $Root) "pics"
Write-Host "Serving: $Root"
Write-Host "URL:     $prefix"
Write-Host "Photos:  $picsDir"
Write-Host ""
Write-Host "Keep this window open while demoing. Press Ctrl+C to stop."
Write-Host "Tip: Chrome or Edge needed for Web Serial. Do not open index.html via file://"
Write-Host ""

Open-DemoBrowser $prefix

$mimes = @{
  ".html" = "text/html; charset=utf-8"
  ".htm"  = "text/html; charset=utf-8"
  ".js"   = "text/javascript; charset=utf-8"
  ".mjs"  = "text/javascript; charset=utf-8"
  ".css"  = "text/css; charset=utf-8"
  ".wasm" = "application/wasm"
  ".task" = "application/octet-stream"
  ".json" = "application/json"
  ".map"  = "application/json"
  ".png"  = "image/png"
  ".jpg"  = "image/jpeg"
  ".jpeg" = "image/jpeg"
  ".svg"  = "image/svg+xml"
  ".txt"  = "text/plain; charset=utf-8"
  ".ico"  = "image/x-icon"
}

try {
  while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $req = $ctx.Request
    $res = $ctx.Response
    try {
      if ($req.HttpMethod -eq "POST") {
        $res.ContentType = "application/json; charset=utf-8"
        if ($req.Url.AbsolutePath -ne "/api/photo") {
          $res.StatusCode = 404
          $payload = '{"ok":false,"error":"not found"}'
        } elseif ($req.ContentLength64 -le 0 -or $req.ContentLength64 -gt 12000000) {
          $res.StatusCode = 413
          $payload = '{"ok":false,"error":"image too large"}'
        } else {
          $reader = New-Object System.IO.StreamReader($req.InputStream, $req.ContentEncoding)
          $raw = $reader.ReadToEnd()
          $reader.Close()
          $body = $raw | ConvertFrom-Json
          $email = if ($null -eq $body.email) { "" } else { ([string]$body.email).Trim() }
          $social = if ($null -eq $body.social) { "" } else { ([string]$body.social).Trim() }
          $image = [string]$body.image
          $emailOk = ($email -eq "") -or ($email -match '^[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+$' -and $email -notmatch '\.\.')
          $socialOk = ($social -eq "") -or ($social.Length -le 64 -and $social -notmatch '[/\\:*?"<>|]' -and $social -notmatch '\.\.')
          $comma = $image.IndexOf(",")
          $needEmail = ($body.emailPhoto -eq $true -and $email -eq "")
          $needSocial = ($body.mention -eq $true -and $social -eq "")
          $blob = $null
          $imageOk = $emailOk -and $socialOk -and -not $needEmail -and -not $needSocial -and -not ($email -eq "" -and $social -eq "") -and $comma -ge 0 -and $image.StartsWith("data:image/")
          if ($imageOk) {
            try { $blob = [Convert]::FromBase64String($image.Substring($comma + 1)) } catch { $blob = $null }
            $jpeg = ($null -ne $blob -and $blob.Length -ge 2 -and $blob[0] -eq 255 -and $blob[1] -eq 216)
            $png = ($null -ne $blob -and $blob.Length -ge 4 -and $blob[0] -eq 137 -and $blob[1] -eq 80 -and $blob[2] -eq 78 -and $blob[3] -eq 71)
            $imageOk = $null -ne $blob -and $blob.Length -ge 32 -and $blob.Length -le 8000000 -and ($jpeg -or $png)
          }
          if (-not $imageOk) {
            $res.StatusCode = 400
            $payload = '{"ok":false,"error":"bad email, social tag, or image"}'
          } else {
            $pics = Join-Path (Split-Path -Parent $Root) "pics"
            New-Item -ItemType Directory -Force -Path $pics | Out-Null
            $emailFlag = "N"
            $mentionFlag = "N"
            if ($body.emailPhoto -eq $true) { $emailFlag = "Y" }
            if ($body.mention -eq $true) { $mentionFlag = "Y" }
            $base = "$emailFlag $mentionFlag"
            if ($email -ne "") { $base = "$base $email" }
            if ($social -ne "") { $base = "$base $social" }
            $stem = $base
            $n = 0
            while (Test-Path -LiteralPath (Join-Path $pics ($stem + ".jpg"))) {
              $n++
              if ($n -ge 10000) { throw "too many photos for this name" }
              $stem = "$base $n"
            }
            $dest = Join-Path $pics ($stem + ".jpg")
            [System.IO.File]::WriteAllBytes($dest, $blob)
            $payload = '{"ok":true,"file":"pics/' + $stem + '.jpg"}'
          }
        }
        $buf = [Text.Encoding]::UTF8.GetBytes($payload)
        $res.ContentLength64 = $buf.LongLength
        $res.OutputStream.Write($buf, 0, $buf.Length)
        continue
      }
      $rel = [Uri]::UnescapeDataString($req.Url.AbsolutePath.TrimStart("/"))
      if ([string]::IsNullOrWhiteSpace($rel)) { $rel = "index.html" }
      $full = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($Root, $rel.Replace("/", [IO.Path]::DirectorySeparatorChar)))
      $rootPrefix = $Root.TrimEnd("\", "/") + [IO.Path]::DirectorySeparatorChar
      if (-not ($full.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -or $full.Equals($Root, [StringComparison]::OrdinalIgnoreCase))) {
        $res.StatusCode = 403
      } elseif (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        $res.StatusCode = 404
      } else {
        $bytes = [System.IO.File]::ReadAllBytes($full)
        $ext = [System.IO.Path]::GetExtension($full).ToLowerInvariant()
        if ($mimes.ContainsKey($ext)) { $res.ContentType = $mimes[$ext] }
        else { $res.ContentType = "application/octet-stream" }
        $res.ContentLength64 = $bytes.LongLength
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
      }
    } catch {
      try { $res.StatusCode = 500 } catch { }
    } finally {
      try { $res.OutputStream.Close() } catch { }
    }
  }
} finally {
  try { $listener.Stop() } catch { }
  try { $listener.Close() } catch { }
}
