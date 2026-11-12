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

# Compute SHA-256 without Get-FileHash. When this script is launched from a
# child powershell.exe under PowerShell 7's PSModulePath, Windows PowerShell
# 5.1 loads the Core Microsoft.PowerShell.Utility and Get-FileHash disappears
# (PowerShell/PowerShell discussion #24630). .NET has no such dependency.
function Get-Sha256Hex {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "")
        }
        finally { $sha.Dispose() }
    }
    finally { $stream.Dispose() }
}

function Release-ComObject {
    param([object]$Object)
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Measure-SlideTextBounds {
    param([object]$Slide, [int]$PhysicalIndex, [double]$SlideWidth, [double]$SlideHeight)
    $measured = 0
    $unavailable = 0
    $warnings = @()
    $shapes = $null
    try {
        $shapes = $Slide.Shapes
        for ($shapeIndex = 1; $shapeIndex -le $shapes.Count; $shapeIndex++) {
            $shape = $null
            $frame = $null
            $range = $null
            try {
                $shape = $shapes.Item($shapeIndex)
                if ([int]$shape.HasTextFrame -eq 0) { continue }
                $frame = $shape.TextFrame
                if ([int]$frame.HasText -eq 0) { continue }
                $range = $frame.TextRange
                $left = [double]$range.BoundLeft
                $top = [double]$range.BoundTop
                $width = [double]$range.BoundWidth
                $height = [double]$range.BoundHeight
                if ($width -le 0 -or $height -le 0) { continue }
                $measured++
                $edges = [ordered]@{
                    left = -$left
                    top = -$top
                    right = $left + $width - $SlideWidth
                    bottom = $top + $height - $SlideHeight
                }
                $overflow = [ordered]@{}
                foreach ($edge in $edges.Keys) {
                    if ($edges[$edge] -gt 1.0) { $overflow[$edge] = [Math]::Round($edges[$edge], 2) }
                }
                if ($overflow.Count) {
                    $warnings += [PSCustomObject]@{
                        physical_index = $PhysicalIndex
                        code = "text-outside-slide"
                        measurement = "com-text-range-bounds"
                        shape_index = $shapeIndex
                        overflow_pt = $overflow
                    }
                }
            }
            catch { $unavailable++ }  # Some WPS shapes omit TextRange metrics.
            finally {
                Release-ComObject $range
                Release-ComObject $frame
                Release-ComObject $shape
            }
        }
    }
    finally { Release-ComObject $shapes }
    return @{ measured = $measured; unavailable = $unavailable; warnings = $warnings }
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
if ($existing.Count -gt 0 -or (Test-Path -LiteralPath (Join-Path $output "render-manifest.json"))) {
    throw "Output directory already contains a render; use a fresh directory: $output"
}

$sourceHashBefore = Get-Sha256Hex $source
$scratchRoot = (Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path
$scratch = [IO.Path]::GetFullPath((Join-Path $scratchRoot ("deckforge-render-" + [guid]::NewGuid().ToString("N"))))
[void](New-Item -ItemType Directory -Path $scratch)
$scratchPptx = Join-Path $scratch ([IO.Path]::GetFileName($source))
Copy-Item -LiteralPath $source -Destination $scratchPptx

$app = $null
$presentation = $null
$slides = $null
$engineName = $null
$ownsApp = $false
$existingApps = @(Get-Process -Name "POWERPNT", "wpp" -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessName })
$rendered = @()
$hiddenIndices = @()
$layoutWarnings = @()
$measuredTextRanges = 0
$unavailableTextRanges = 0
$slideCount = 0
# Effective export height. When -Height is not passed explicitly it is derived
# from the source slide aspect ratio (PageSetup) so non-16:9 decks are neither
# stretched nor rejected. Kept separate from $Height so ValidateRange only
# constrains user input.
$renderHeight = $Height
$slideWidthPt = 0.0
$slideHeightPt = 0.0

try {
    $started = Start-PresentationApp -Requested $Engine
    $engineName = $started.Name
    $app = $started.App
    $processName = if ($engineName -eq "powerpoint") { "POWERPNT" } else { "wpp" }
    # COM can return an application the user is already working in.
    $ownsApp = $processName -notin $existingApps -and $app.Presentations.Count -eq 0
    if ($ownsApp) {
        try { $app.DisplayAlerts = 0 } catch { }
        try { $app.Visible = 0 } catch { }
    }

    try {
        # Open a scratch copy. ReadOnly=-1, Untitled=0, WithWindow=0.
        $presentation = $app.Presentations.Open($scratchPptx, -1, 0, 0)
    }
    catch {
        # Some WPS builds expose a shorter Open signature. The source remains safe
        # because this is still the scratch copy.
        $presentation = $app.Presentations.Open($scratchPptx)
    }

    $pageSetup = $null
    try {
        $pageSetup = $presentation.PageSetup
        $slideWidthPt = [double]$pageSetup.SlideWidth
        $slideHeightPt = [double]$pageSetup.SlideHeight
        if (-not $PSBoundParameters.ContainsKey('Height') -and $slideWidthPt -gt 0 -and $slideHeightPt -gt 0) {
            $renderHeight = [int][Math]::Round($Width * $slideHeightPt / $slideWidthPt)
        }
    }
    catch { }
    finally { Release-ComObject $pageSetup }

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
            $slide.Export($path, "PNG", $Width, $renderHeight)
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Engine did not create slide image: $path"
            }
            $rendered += [PSCustomObject]@{
                physical_index = $i
                hidden = $isHidden
                file = [IO.Path]::GetFileName($path)
            }
            if ($slideWidthPt -gt 0 -and $slideHeightPt -gt 0) {
                $bounds = Measure-SlideTextBounds $slide $i $slideWidthPt $slideHeightPt
                $measuredTextRanges += $bounds.measured
                $unavailableTextRanges += $bounds.unavailable
                $layoutWarnings += $bounds.warnings
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
            if ($bitmap.Width -ne $Width -or $bitmap.Height -ne $renderHeight) {
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
    if ($null -ne $app -and $ownsApp) {
        try { if ($app.Presentations.Count -eq 0) { $app.Quit() } } catch { }
    }
    Release-ComObject $slides
    Release-ComObject $presentation
    Release-ComObject $app
    $scratchParent = [IO.Directory]::GetParent($scratch).FullName
    if ($scratchParent -eq [IO.DirectoryInfo]::new($scratchRoot).FullName.TrimEnd('\') -and
        [IO.Path]::GetFileName($scratch) -match '^deckforge-render-[0-9a-f]{32}$') {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$sourceHashAfter = Get-Sha256Hex $source
if ($sourceHashBefore -ne $sourceHashAfter) {
    throw "Source file changed during render: $source"
}

$manifest = [ordered]@{
    source = $source
    source_sha256 = $sourceHashAfter
    engine = $engineName
    width = $Width
    height = $renderHeight
    include_hidden = [bool]$IncludeHidden
    slide_count = $slideCount
    hidden_physical_indices = @($hiddenIndices)
    rendered = @($rendered)
    text_bounds = @{
        method = "com-text-range-bounds"
        measured_text_ranges = $measuredTextRanges
        unavailable_text_ranges = $unavailableTextRanges
        tolerance_pt = 1.0
        scope = "Top-level text frames with available layout bounds on rendered slides."
    }
    layout_warnings = @($layoutWarnings)
}

$manifestPath = Join-Path $output "render-manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output ("Rendered {0} slide(s) with {1} -> {2}" -f $rendered.Count, $engineName, $output)
Write-Output ("Manifest: {0}" -f $manifestPath)
