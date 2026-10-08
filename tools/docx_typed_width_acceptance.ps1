param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$widthWord = $null
$widthDocument = $null
$widthObservations = @()
try {
    $widthRoot = (Resolve-Path -LiteralPath $FixtureRoot).Path
    $widthFolders = @(Get-ChildItem -LiteralPath $widthRoot -Directory -Filter 'test_typed_edit_then_remove_ov*')
    if ($widthFolders.Count -ne 2) { throw 'Expected the two own typed/legacy width fixtures' }
    $widthWord = New-Object -ComObject Word.Application
    $widthWord.Visible = $false
    $widthWord.DisplayAlerts = 0
    $widthWord.AutomationSecurity = 3
    foreach ($widthFolder in $widthFolders) {
        foreach ($widthName in @('edited-0.docx', 'edited-1.docx')) {
            $widthPath = Join-Path $widthFolder.FullName $widthName
            $widthHash = (Get-FileHash -LiteralPath $widthPath -Algorithm SHA256).Hash
            $widthDocument = $widthWord.Documents.Open($widthPath, $false, $true)
            $widthTable = $widthDocument.Tables.Item(1)
            $widthCell = $widthTable.Cell(1, 1)
            # Word exposes preferences at its own precision, distinct from exact XML.
            if ($widthTable.PreferredWidthType -ne 2 -or
                [math]::Abs($widthTable.PreferredWidth - 75.001) -gt 0.02 -or
                $widthCell.PreferredWidthType -ne 3 -or
                [math]::Abs($widthCell.PreferredWidth - 12.125) -gt 0.05) {
                throw 'Word preferred width type/value differs'
            }
            $widthObservations += @{
                fixture=$widthFolder.Name; file=$widthName;
                table_type=$widthTable.PreferredWidthType; table_percent=$widthTable.PreferredWidth;
                cell_type=$widthCell.PreferredWidthType; cell_points=$widthCell.PreferredWidth
            }
            $widthDocument.Close(0)
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($widthDocument)
            $widthDocument = $null
            if ((Get-FileHash -LiteralPath $widthPath -Algorithm SHA256).Hash -ne $widthHash) {
                throw 'Word changed a read-only fixture'
            }
        }
    }
    @{success=$true; program='Microsoft Word'; version=$widthWord.Version; build=$widthWord.Build;
      observations=$widthObservations} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $widthDocument) { $widthDocument.Close(0) }
    if ($null -ne $widthWord) {
        $widthWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($widthWord)
    }
}
