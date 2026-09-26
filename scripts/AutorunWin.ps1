# Static file server for CamWalkingGame (no Python required).
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

Write-Host "Serving: $Root"
Write-Host "URL:     $prefix"
Write-Host ""
Write-Host "Keep this window open while demoing. Press Ctrl+C to stop."
Write-Host "Tip: Chrome or Edge needed for Web Serial. Do not open index.html via file://"
Write-Host ""

Start-Process $prefix

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
        } else {
          $reader = New-Object System.IO.StreamReader($req.InputStream, $req.ContentEncoding)
          $raw = $reader.ReadToEnd()
          $reader.Close()
          $body = $raw | ConvertFrom-Json
          $email = [string]$body.email
          $email = $email.Trim()
          $image = [string]$body.image
          $emailOk = $email -match '^[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+$' -and $email -notmatch '\.\.'
          $comma = $image.IndexOf(",")
          if (-not $emailOk -or $comma -lt 0 -or -not $image.StartsWith("data:image/")) {
            $res.StatusCode = 400
            $payload = '{"ok":false,"error":"bad email or image"}'
          } else {
            $b64 = $image.Substring($comma + 1)
            $blob = [Convert]::FromBase64String($b64)
            $pics = Join-Path (Split-Path -Parent $Root) "pics"
            New-Item -ItemType Directory -Force -Path $pics | Out-Null
            $stem = $email
            $n = 0
            while (Test-Path -LiteralPath (Join-Path $pics ($stem + ".jpg"))) {
              $n++
              if ($n -ge 10000) { throw "too many photos for this email" }
              $stem = "$email $n"
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
