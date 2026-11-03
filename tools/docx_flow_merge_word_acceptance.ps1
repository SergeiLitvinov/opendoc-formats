param([Parameter(Mandatory=$true)][string]$CaseRoot,
      [ValidateSet('full','top','bottom','plain')][string]$Profile='full')
$ErrorActionPreference = 'Stop'
$mergeRoot = [IO.Path]::GetFullPath($CaseRoot)
$mergeWorkspace = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
if (-not $mergeRoot.StartsWith($mergeWorkspace+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Fixtures outside workspace' }
$mergeWord = $null
$mergeDocument = $null
$mergeObservations = @()
$mergeExpectedTexts = switch ($Profile) {
    'top' { @('Top merge','R1C3') }
    'bottom' { @('Tall merge','R2C2','R2C3','R3C2','R3C3') }
    'plain' { @('R2C2','R2C3','R3C2','R3C3') }
    default { @('Top merge','R1C3','Tall merge','R2C2','R2C3','R3C2','R3C3') }
}
$mergeEditSource = if ($Profile -eq 'top') { 'Top merge' } elseif ($Profile -eq 'plain') { 'R2C2' } else { 'Tall merge' }
$mergeEditText = if ($Profile -eq 'full') { 'Edited tall cell' } else { 'Edited cell' }
try {
    $mergeWord = New-Object -ComObject Word.Application
    $mergeWord.Visible = $false
    $mergeWord.DisplayAlerts = 0
    $mergeWord.AutomationSecurity = 3
    foreach ($mergeName in @('flow', 'native-0', 'native-1')) {
        $mergePath = Join-Path $mergeRoot ($mergeName+'.docx')
        $mergeHash = (Get-FileHash -LiteralPath $mergePath -Algorithm SHA256).Hash
        $mergeDocument = $mergeWord.Documents.Open($mergePath, $false, $true, $false)
        $mergeTable = $mergeDocument.Tables.Item(1)
        $mergeCells = @()
        foreach ($mergeCell in $mergeTable.Range.Cells) {
            $mergeText = $mergeCell.Range.Text.Trim([char]13,[char]7)
            $mergeWidth = [double]$mergeCell.Width
            $mergeCells += @{text=$mergeText; row=$mergeCell.RowIndex; column=$mergeCell.ColumnIndex; width=$mergeWidth}
            $mergeExpectedWidth = if ($mergeText -eq 'Top merge') { 200 } else { 100 }
            if ([math]::Abs($mergeWidth-$mergeExpectedWidth) -gt 0.1) { throw 'Merged cell width changed' }
        }
        $mergeActualTexts = @($mergeCells | ForEach-Object { $_.text })
        if ($mergeCells.Count -ne $mergeExpectedTexts.Count -or
            @(Compare-Object $mergeActualTexts $mergeExpectedTexts).Count) { throw 'Native merge structure changed' }
        if ($mergeTable.Borders.Item(1).LineWidth -ne 8 -or $mergeTable.Borders.Item(1).Color -ne 0) { throw 'Border changed' }
        $mergeDocument.ExportAsFixedFormat((Join-Path $mergeRoot ($mergeName+'.pdf')), 17)
        $mergeObservations += @{file=$mergeName; pages=$mergeDocument.ComputeStatistics(2); cells=$mergeCells}
        $mergeDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($mergeDocument)
        $mergeDocument = $null
        if ((Get-FileHash -LiteralPath $mergePath -Algorithm SHA256).Hash -ne $mergeHash) { throw 'Read-only source modified' }
    }
    $mergeEdited = Join-Path $mergeRoot 'native-edit.docx'
    Copy-Item -LiteralPath (Join-Path $mergeRoot 'flow.docx') -Destination $mergeEdited
    $mergeDocument = $mergeWord.Documents.Open($mergeEdited, $false, $false, $false)
    $mergeFound = $false
    foreach ($mergeCell in $mergeDocument.Tables.Item(1).Range.Cells) {
        if ($mergeCell.Range.Text.Trim([char]13,[char]7) -eq $mergeEditSource) {
            $mergeCell.Range.Text = $mergeEditText
            $mergeFound = $true
            break
        }
    }
    if (-not $mergeFound) { throw 'Merged cell missing for native edit' }
    $mergeDocument.Save()
    $mergeDocument.Close(0)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($mergeDocument)
    $mergeDocument = $null
    @{success=$true; profile=$Profile; edit_source=$mergeEditSource; edit_text=$mergeEditText;
      program='Microsoft Word'; version=$mergeWord.Version; build=$mergeWord.Build;
      observations=$mergeObservations} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $mergeDocument) { $mergeDocument.Close(0) }
    if ($null -ne $mergeWord) {
        $mergeWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($mergeWord)
    }
}
