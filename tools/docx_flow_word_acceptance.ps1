param([Parameter(Mandatory=$true)][string]$CaseRoot)
$ErrorActionPreference = 'Stop'
$flowRoot = [IO.Path]::GetFullPath($CaseRoot)
$flowWorkspace = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
if (-not $flowRoot.StartsWith($flowWorkspace+'\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Acceptance fixtures must be inside the workspace'
}
$flowWord = $null
$flowDocument = $null
$flowObservations = @()
try {
    $flowWord = New-Object -ComObject Word.Application
    $flowWord.Visible = $false
    $flowWord.DisplayAlerts = 0
    $flowWord.AutomationSecurity = 3
    foreach ($flowName in @('flow', 'native-0', 'native-1')) {
        $flowPath = Join-Path $flowRoot ($flowName+'.docx')
        $flowHash = (Get-FileHash -LiteralPath $flowPath -Algorithm SHA256).Hash
        $flowDocument = $flowWord.Documents.Open($flowPath, $false, $true, $false)
        $flowTable = $flowDocument.Tables.Item(1)
        if ($flowTable.Rows.Count -ne 2 -or $flowTable.Columns.Count -ne 2) { throw 'Native table shape changed' }
        $flowWidths = @()
        for ($flowRow=1; $flowRow -le 2; $flowRow++) {
            for ($flowColumn=1; $flowColumn -le 2; $flowColumn++) {
                $flowCell = $flowTable.Cell($flowRow, $flowColumn)
                $flowText = $flowCell.Range.Text.Trim([char]13,[char]7)
                if ($flowText -ne ('R'+($flowRow+1)+'C'+$flowColumn)) { throw 'Native table text changed' }
                $flowWidths += [double]$flowCell.Width
                if ([math]::Abs($flowCell.Width - 100) -gt 0.1) { throw 'Native column width changed' }
            }
        }
        if ($flowTable.Borders.Item(1).LineWidth -ne 8 -or $flowTable.Borders.Item(1).Color -ne 0) {
            throw 'Native border width/color changed'
        }
        $flowOutline = $flowDocument.Range($flowTable.Range.End, $flowTable.Range.End+1).ParagraphFormat.OutlineLevel
        if ($flowOutline -ne 2) { throw 'Native heading role changed' }
        $flowDocument.ExportAsFixedFormat((Join-Path $flowRoot ($flowName+'.pdf')), 17)
        $flowObservations += @{file=$flowName; pages=$flowDocument.ComputeStatistics(2); widths=$flowWidths; outline=$flowOutline}
        $flowDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($flowDocument)
        $flowDocument = $null
        if ((Get-FileHash -LiteralPath $flowPath -Algorithm SHA256).Hash -ne $flowHash) { throw 'Word modified read-only fixture' }
    }
    $flowEdited = Join-Path $flowRoot 'native-edit.docx'
    Copy-Item -LiteralPath (Join-Path $flowRoot 'flow.docx') -Destination $flowEdited
    $flowDocument = $flowWord.Documents.Open($flowEdited, $false, $false, $false)
    $flowDocument.Tables.Item(1).Cell(1,1).Range.Text = 'Edited cell'
    $flowDocument.Save()
    $flowDocument.Close(0)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($flowDocument)
    $flowDocument = $null
    @{success=$true; program='Microsoft Word'; version=$flowWord.Version; build=$flowWord.Build;
      observations=$flowObservations} | ConvertTo-Json -Depth 5
}
finally {
    if ($null -ne $flowDocument) { $flowDocument.Close(0) }
    if ($null -ne $flowWord) {
        $flowWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($flowWord)
    }
}
