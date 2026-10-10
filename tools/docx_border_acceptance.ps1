param([Parameter(Mandatory=$true)][string]$FixtureRoot, [switch]$VerifyFinal)
$ErrorActionPreference = 'Stop'
$borderWord = $null
$borderDocument = $null
$borderObservations = @()
try {
    $borderRoot = (Resolve-Path -LiteralPath $FixtureRoot).Path
    $workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $qaRoot = Join-Path $workspaceRoot '.opendoc-formats'
    if (-not $borderRoot.StartsWith($qaRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only own workspace QA fixtures are accepted'
    }
    $borderWord = New-Object -ComObject Word.Application
    $borderWord.Visible = $false
    $borderWord.DisplayAlerts = 0
    $borderWord.AutomationSecurity = 3
    $borderNames = if ($VerifyFinal) { @('native-cycle.docx') } else { @('own.docx','cycle-0.docx','cycle-1.docx','typed-edit.docx') }
    $baseline = $null
    foreach ($borderName in $borderNames) {
        $borderPath = Join-Path $borderRoot $borderName
        $borderHash = (Get-FileHash -LiteralPath $borderPath -Algorithm SHA256).Hash
        $borderDocument = $borderWord.Documents.Open($borderPath, $false, $true)
        $borderTable = $borderDocument.Tables.Item(1)
        $borderValues = @()
        foreach ($borderIndex in @(-1,-2,-3,-4,-5,-6)) {
            $borderObject = $borderTable.Borders.Item($borderIndex)
            $borderValues += @{side=$borderIndex;style=$borderObject.LineStyle;width=$borderObject.LineWidth;color=$borderObject.Color}
        }
        if ($VerifyFinal) {
            if ($borderValues[0].style -ne 7 -or $borderValues[0].color -ne 255) { throw 'Native edit lost after public cycle' }
        } elseif ($borderName -eq 'own.docx') {
            if (@($borderValues | Where-Object style -ne 1).Count) { throw 'Own source must have six single borders' }
            $baseline = $borderValues | ConvertTo-Json -Compress
        } elseif ($borderName -eq 'typed-edit.docx') {
            if ($borderValues[0].style -ne 7) { throw 'Typed double border was not rendered by Word' }
        } elseif (($borderValues | ConvertTo-Json -Compress) -ne $baseline) {
            throw 'Native border properties differ from original'
        }
        $borderObservations += @{file=$borderName;borders=$borderValues;pages=$borderDocument.ComputeStatistics(2)}
        $borderDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($borderDocument)
        $borderDocument = $null
        if ((Get-FileHash -LiteralPath $borderPath -Algorithm SHA256).Hash -ne $borderHash) { throw 'Read-only source changed' }
    }
    if (-not $VerifyFinal) {
        $editPath = Join-Path $borderRoot 'native-edit.docx'
        Copy-Item -LiteralPath (Join-Path $borderRoot 'cycle-1.docx') -Destination $editPath
        $borderDocument = $borderWord.Documents.Open($editPath, $false, $false)
        $borderObject = $borderDocument.Tables.Item(1).Borders.Item(-1)
        $borderObject.LineStyle = 7
        $borderObject.Color = 255
        $borderDocument.Save()
        $borderDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($borderDocument)
        $borderDocument = $null
    }
    @{success=$true;program='Microsoft Word';version=$borderWord.Version;build=$borderWord.Build;
      observations=$borderObservations} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $borderDocument) { $borderDocument.Close(0) }
    if ($null -ne $borderWord) {
        $borderWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($borderWord)
    }
}
