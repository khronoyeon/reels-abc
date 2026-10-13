# Windows 내장 글자 인식(Windows.Media.Ocr)으로 이미지 속 글자 읽기 — 타이틀 자막용
# 출력: 줄마다 JSON {file, text, top(위쪽 끝, 0~1 아래가 0), h(높이 0~1)}
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
  })[0]
function Await($op, [Type]$type) {
  $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  $null = $task.Wait(-1)
  $task.Result
}

$engine = $null
$ko = New-Object Windows.Globalization.Language('ko')
if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($ko)) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($ko) }
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { exit 0 }

foreach ($p in $Paths) {
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $H = [double]$bitmap.PixelHeight
    foreach ($line in $result.Lines) {
      $rects = @($line.Words | ForEach-Object { $_.BoundingRect })
      if ($rects.Count -eq 0) { continue }
      $top = ($rects | ForEach-Object { $_.Y } | Measure-Object -Minimum).Minimum
      $bottom = ($rects | ForEach-Object { $_.Y + $_.Height } | Measure-Object -Maximum).Maximum
      $left = ($rects | ForEach-Object { $_.X } | Measure-Object -Minimum).Minimum
      [pscustomobject]@{ file = $p; text = $line.Text; top = 1 - $top / $H; h = ($bottom - $top) / $H; left = $left / [double]$bitmap.PixelWidth } | ConvertTo-Json -Compress
    }
    $stream.Dispose()
  } catch {
    # 한 장이 실패해도 나머지는 계속
  }
}
