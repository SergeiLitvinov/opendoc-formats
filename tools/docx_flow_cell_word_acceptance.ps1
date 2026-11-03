param([Parameter(Mandatory=$true)][string]$CaseRoot)
$ErrorActionPreference = 'Stop'
$cellRoot = [IO.Path]::GetFullPath($CaseRoot)
$cellWorkspace = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
if (-not $cellRoot.StartsWith($cellWorkspace+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Fixtures outside workspace' }
$cellExpected = @(Get-Content -LiteralPath (Join-Path $cellRoot 'expected.json') -Raw | ConvertFrom-Json)
$cellWord = $null
$cellDocument = $null
$cellObservations = @()
try {
    $cellWord = New-Object -ComObject Word.Application
    $cellWord.Visible = $false
    $cellWord.DisplayAlerts = 0
    $cellWord.AutomationSecurity = 3
    foreach ($cellName in @('flow','native-0','native-1')) {
        $cellPath = Join-Path $cellRoot ($cellName+'.docx')
        $cellHash = (Get-FileHash -LiteralPath $cellPath -Algorithm SHA256).Hash
        $cellDocument = $cellWord.Documents.Open($cellPath,$false,$true,$false)
        $cellTable = $cellDocument.Tables.Item(1)
        $cellActual = @()
        foreach ($cellNative in $cellTable.Range.Cells) {
            $cellText = $cellNative.Range.Text.Trim([char]13,[char]7)
            $cellPlan = @($cellExpected | Where-Object { $_.text -eq $cellText })
            if ($cellPlan.Count -ne 1) { throw 'Native logical cell text changed' }
            $cellPlan = $cellPlan[0]
            if ([math]::Abs([double]$cellNative.Width-$cellPlan.width) -gt .1) { throw 'Native cell width changed' }
            $cellBorders = @()
            foreach ($cellSide in $cellPlan.sides) {
                $cellBorder = $cellNative.Borders.Item([int]$cellSide.id)
                if ($cellBorder.LineWidth -ne $cellSide.size -or $cellBorder.Color -ne $cellSide.color -or
                    $cellBorder.LineStyle -ne 1) { throw ('Native cell border changed: '+$cellText+' '+$cellSide.name) }
                $cellBorders += @{side=$cellSide.name; size=$cellBorder.LineWidth; color=$cellBorder.Color}
            }
            $cellActual += @{text=$cellText; width=[double]$cellNative.Width; borders=$cellBorders}
        }
        if ($cellActual.Count -ne $cellExpected.Count) { throw 'Native logical cell count changed' }
        $cellDocument.ExportAsFixedFormat((Join-Path $cellRoot ($cellName+'.pdf')),17)
        $cellObservations += @{file=$cellName; pages=$cellDocument.ComputeStatistics(2); cells=$cellActual}
        $cellDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($cellDocument)
        $cellDocument = $null
        if ((Get-FileHash -LiteralPath $cellPath -Algorithm SHA256).Hash -ne $cellHash) { throw 'Read-only source changed' }
    }
    $cellEdited = Join-Path $cellRoot 'native-edit.docx'
    Copy-Item -LiteralPath (Join-Path $cellRoot 'flow.docx') -Destination $cellEdited
    $cellDocument = $cellWord.Documents.Open($cellEdited,$false,$false,$false)
    $cellEditSource = $cellExpected[0].text
    foreach ($cellNative in $cellDocument.Tables.Item(1).Range.Cells) {
        if ($cellNative.Range.Text.Trim([char]13,[char]7) -eq $cellEditSource) {
            $cellNative.Range.Text = 'Edited cell'
            break
        }
    }
    $cellDocument.Save()
    $cellDocument.Close(0)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($cellDocument)
    $cellDocument = $null
    @{success=$true; program='Microsoft Word'; version=$cellWord.Version; build=$cellWord.Build;
      edit_source=$cellEditSource; observations=$cellObservations} | ConvertTo-Json -Depth 9
}
finally {
    if ($null -ne $cellDocument) { $cellDocument.Close(0) }
    if ($null -ne $cellWord) {
        $cellWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($cellWord)
    }
}
