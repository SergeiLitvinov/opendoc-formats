param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
if (@(Get-Process WINWORD -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Run this optional fixture check when no other Word session is open'
}
$anatomyRoot = [IO.Path]::GetFullPath($FixtureRoot)
$anatomyWord = $null
$anatomyDocument = $null
$anatomyResults = @()
$anatomyOldLinks = $null
try {
    $anatomyWord = New-Object -ComObject Word.Application
    $anatomyWord.Visible = $false
    $anatomyWord.DisplayAlerts = 0
    $anatomyWord.AutomationSecurity = 3
    $anatomyOldLinks = $anatomyWord.Options.UpdateLinksAtOpen
    $anatomyWord.Options.UpdateLinksAtOpen = $false
    foreach ($anatomyName in @('source', 'edited')) {
        $anatomyPath = Join-Path $anatomyRoot ($anatomyName + '.docx')
        $anatomyPdf = Join-Path $anatomyRoot ($anatomyName + '.pdf')
        if (Test-Path -LiteralPath $anatomyPdf) { throw 'PDF acceptance output already exists' }
        $anatomyHash = (Get-FileHash -LiteralPath $anatomyPath -Algorithm SHA256).Hash
        $anatomyDocument = $anatomyWord.Documents.Open($anatomyPath, $false, $true, $false)
        $anatomyText = [regex]::Replace($anatomyDocument.Content.Text.Replace([string][char]7, ' '), '\s+', ' ').Trim()
        $anatomyWidths = @()
        foreach ($anatomyCell in $anatomyDocument.Tables.Item(1).Rows.Item(1).Cells) {
            $anatomyWidths += [double]$anatomyCell.Width
        }
        $anatomyResults += @{
            file=$anatomyName; text=$anatomyText; pages=[int]$anatomyDocument.ComputeStatistics(2);
            tables=[int]$anatomyDocument.Tables.Count; images=[int]$anatomyDocument.InlineShapes.Count;
            hyperlinks=[int]$anatomyDocument.Hyperlinks.Count; widths_points=$anatomyWidths
        }
        $anatomyDocument.ExportAsFixedFormat($anatomyPdf, 17)
        $anatomyDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($anatomyDocument)
        $anatomyDocument = $null
        if ((Get-FileHash -LiteralPath $anatomyPath -Algorithm SHA256).Hash -ne $anatomyHash) {
            throw 'Word changed a read-only fixture'
        }
    }
    $anatomyBefore, $anatomyAfter = $anatomyResults
    if ($anatomyAfter.text -ne $anatomyBefore.text.Replace('Before', 'Edited')) { throw 'Unexpected Word content change' }
    foreach ($anatomyField in @('pages', 'tables', 'images', 'hyperlinks')) {
        if ($anatomyBefore[$anatomyField] -ne $anatomyAfter[$anatomyField]) { throw "Word changed $anatomyField" }
    }
    if ($anatomyBefore.images -ne 1 -or $anatomyBefore.hyperlinks -ne 1) { throw 'Word did not recognize native fixture objects' }
    if ($anatomyBefore.widths_points.Count -ne $anatomyAfter.widths_points.Count) { throw 'Word column count changed' }
    for ($anatomyIndex = 0; $anatomyIndex -lt $anatomyBefore.widths_points.Count; $anatomyIndex++) {
        if ([math]::Abs($anatomyBefore.widths_points[$anatomyIndex] - $anatomyAfter.widths_points[$anatomyIndex]) -gt 0.1) {
            throw 'Word changed a native table width'
        }
    }
    @{program='Microsoft Word'; version=$anatomyWord.Version; build=$anatomyWord.Build;
      success=$true; observations=$anatomyResults} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $anatomyDocument) { $anatomyDocument.Close(0) }
    if ($null -ne $anatomyWord) {
        if ($null -ne $anatomyOldLinks) { $anatomyWord.Options.UpdateLinksAtOpen = $anatomyOldLinks }
        $anatomyWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($anatomyWord)
    }
}
