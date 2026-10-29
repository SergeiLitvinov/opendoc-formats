param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('reference','render')][string]$Stage='reference'
)

# Own fixture from tests.writers.test_pptx_source_geometry.fixture. Never attach
# to an existing app; sources open read-only and macros remain disabled.
$ErrorActionPreference='Stop'
if (Get-Process -Name POWERPNT -ErrorAction SilentlyContinue) { throw 'PowerPoint already running' }
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$nativeApp=$null
try {
    $nativeApp=New-Object -ComObject PowerPoint.Application
    $nativeApp.AutomationSecurity=3
    $nativeApp.DisplayAlerts=1
    $fileName=if ($Stage -eq 'reference') { 'source.pptx' } else { 'library.pptx' }
    $deck=$nativeApp.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        if ($Stage -eq 'reference') {
            $child=$deck.Slides.Item(1).Shapes.Item(1)
            while ($child.Type -eq 6) { $child=$child.GroupItems.Item(1) }
            $child.Left=$child.Left+2.5
            $child.Top=$child.Top+5
            $child.Width=$child.Width+10
            $child.Height=$child.Height+20
            $child.Rotation=$child.Rotation+17
            $deck.SaveAs((Join-Path $nativeRoot 'native.pptx'),24)
            $deck.SaveAs((Join-Path $nativeRoot 'native.pdf'),32)
        } else {
            $deck.SaveAs((Join-Path $nativeRoot 'library.pdf'),32)
        }
    } finally { $deck.Close() }
    [pscustomobject]@{
        version=$nativeApp.Version
        source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $originalHash)
        stage=$Stage
    } | ConvertTo-Json -Compress
} finally {
    if ($null -ne $nativeApp) { $nativeApp.Quit() }
}
