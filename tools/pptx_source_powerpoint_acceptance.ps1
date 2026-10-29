param([Parameter(Mandatory=$true)][string]$Root)

# Owned fixture from tests.readers.test_pptx_source_package. Read-only source,
# macros disabled, no user-owned PowerPoint instance or presentation touched.
if (Get-Process -Name POWERPNT -ErrorAction SilentlyContinue) {
    throw 'Native acceptance requires a separate PowerPoint instance; an existing application is running'
}
$acceptanceRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $acceptanceRoot 'independent.pptx'
$sourceHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$nativePowerPoint=$null
try {
    $nativePowerPoint=New-Object -ComObject PowerPoint.Application
    $nativePowerPoint.AutomationSecurity=3
    $nativePowerPoint.DisplayAlerts=1
    $nativeDeck=$nativePowerPoint.Presentations.Open($sourcePath,-1,0,0)
    try {
        $nativeDeck.Slides.Item(1).Shapes.Item(1).TextFrame.TextRange.Runs(1).Text='Native accepted edit'
        $nativeDeck.SaveAs((Join-Path $acceptanceRoot 'native-edit.pdf'),32)
    } finally { $nativeDeck.Close() }
    $libraryDeck=$nativePowerPoint.Presentations.Open((Join-Path $acceptanceRoot 'library.pptx'),-1,0,0)
    try {
        if ($libraryDeck.Slides.Item(1).Shapes.Item(1).TextFrame.TextRange.Text -ne 'Native accepted edit') {
            throw 'Native text differs'
        }
        $libraryDeck.SaveAs((Join-Path $acceptanceRoot 'library.pdf'),32)
        $libraryDeck.Slides.Item(1).Shapes.Item(1).TextFrame.TextRange.Runs(1).Text='After PowerPoint edit'
        $libraryDeck.SaveAs((Join-Path $acceptanceRoot 'native-reedited.pptx'),24)
    } finally { $libraryDeck.Close() }
    [pscustomobject]@{
        version=$nativePowerPoint.Version
        source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $sourceHash)
        success=$true
    } | ConvertTo-Json -Compress
} finally {
    if ($null -ne $nativePowerPoint) { $nativePowerPoint.Quit() }
}
