[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPptx,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [ValidateSet("auto", "powerpoint", "wps")]
    [string]$Engine = "auto",

    [ValidateRange(320, 7680)]
    [int]$Width = 1920,

    [ValidateRange(180, 4320)]
    [int]$Height = 1080,

    [switch]$IncludeHidden
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Release-ComObject {
    param([object]$Object)
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Start-PresentationApp {
    param([string]$Requested)

    $candidates = switch ($Requested) {
        "powerpoint" { @(@{ Name = "powerpoint"; ProgId = "PowerPoint.Application" }) }
        "wps" { @(@{ Name = "wps"; ProgId = "KWPP.Application" }) }
        default {
            @(
                @{ Name = "powerpoint"; ProgId = "PowerPoint.Application" },
                @{ Name = "wps"; ProgId = "KWPP.Application" }
            )
        }
    }

    foreach ($candidate in $candidates) {
        try {
            $type = [Type]::GetTypeFromProgID($candidate.ProgId, $true)
            $app = [Activator]::CreateInstance($type)
            return @{ Name = $candidate.Name; App = $app }
        }
        catch {
            if ($Requested -ne "auto") { throw }
        }
    }
    throw "No supported presentation engine is registered (PowerPoint or WPS)."
}

$source = (Resolve-Path -LiteralPath $InputPptx).Path
if ([IO.Path]::GetExtension($source).ToLowerInvariant() -ne ".pptx") {
    throw "Input must be a .pptx file: $source"
}

$output = [IO.Path]::GetFullPath($OutputDir)
[void](New-Item -ItemType Directory -Path $output -Force)
$existing = @(Get-ChildItem -LiteralPath $output -File -Filter "slide-*.png" -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    throw "Output directory already contains slide-*.png files; use an empty directory: $output"
}

$sourceHashBefore = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$scratch = Join-Path $env:TEMP ("deckforge-render-" + [guid]::NewGuid().ToString("N"))
[void](New-Item -ItemType Directory -Path $scratch)
$scratchPptx = Join-Path $scratch ([IO.Path]::GetFileName($source))
Copy-Item -LiteralPath $source -Destination $scratchPptx

$app = $null
$presentation = $null
$slides = $null
$engineName = $null
$rendered = @()
$hiddenIndices = @()
$slideCount = 0

try {
    $started = Start-PresentationApp -Requested $Engine
    $engineName = $started.Name
    $app = $started.App
    try { $app.DisplayAlerts = 0 } catch { }
    try { $app.Visible = 0 } catch { }

    try {
        # Open a scratch copy. ReadOnly=-1, Untitled=0, WithWindow=0.
        $presentation = $app.Presentations.Open($scratchPptx, -1, 0, 0)
    }
    catch {
        # Some WPS builds expose a shorter Open signature. The source remains safe
        # because this is still the scratch copy.
        $presentation = $app.Presentations.Open($scratchPptx)
    }

    $slides = $presentation.Slides
    $slideCount = [int]$slides.Count
    for ($i = 1; $i -le $slideCount; $i++) {
        $slide = $null
        try {
            $slide = $slides.Item($i)
            $isHidden = $false
            try { $isHidden = ([int]$slide.SlideShowTransition.Hidden -ne 0) } catch { }
            if ($isHidden) { $hiddenIndices += $i }
            if ($isHidden -and -not $IncludeHidden) { continue }

            $path = Join-Path $output ("slide-{0:D3}.png" -f $i)
            $slide.Export($path, "PNG", $Width, $Height)
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Engine did not create slide image: $path"
            }
            $rendered += [PSCustomObject]@{
                physical_index = $i
                hidden = $isHidden
                file = [IO.Path]::GetFileName($path)
            }
        }
        finally {
            Release-ComObject $slide
        }
    }

    Add-Type -AssemblyName System.Drawing
    foreach ($entry in $rendered) {
        $bitmap = $null
        try {
            $bitmap = [Drawing.Image]::FromFile((Join-Path $output $entry.file))
            if ($bitmap.Width -ne $Width -or $bitmap.Height -ne $Height) {
                throw "Unexpected image size for $($entry.file): $($bitmap.Width)x$($bitmap.Height)"
            }
        }
        finally {
            if ($null -ne $bitmap) { $bitmap.Dispose() }
        }
    }
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch { }
    }
    if ($null -ne $app) {
        try { $app.Quit() } catch { }
    }
    Release-ComObject $slides
    Release-ComObject $presentation
    Release-ComObject $app
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}

$sourceHashAfter = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if ($sourceHashBefore -ne $sourceHashAfter) {
    throw "Source file changed during render: $source"
}

$manifest = [ordered]@{
    source = $source
    source_sha256 = $sourceHashAfter
    engine = $engineName
    width = $Width
    height = $Height
    include_hidden = [bool]$IncludeHidden
    slide_count = $slideCount
    hidden_physical_indices = @($hiddenIndices)
    rendered = @($rendered)
}

$manifestPath = Join-Path $output "render-manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output ("Rendered {0} slide(s) with {1} -> {2}" -f $rendered.Count, $engineName, $output)
Write-Output ("Manifest: {0}" -f $manifestPath)
