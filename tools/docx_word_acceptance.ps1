param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$wordCheck = $null
$documentCheck = $null
$rootCheck = [IO.Path]::GetFullPath($FixtureRoot)
$observationsCheck = @()
try {
    $wordCheck = New-Object -ComObject Word.Application
    $wordCheck.Visible = $false
    $wordCheck.DisplayAlerts = 0
    $wordCheck.AutomationSecurity = 3
    foreach ($caseCheck in @('test_smart_tag_text_and_wrappe0', 'test_percentage_table_widths_s0')) {
        $baselineCheck = $null
        foreach ($fileCheck in @('source.docx', 'cycle-0.docx', 'cycle-1.docx')) {
            $pathCheck = Join-Path (Join-Path $rootCheck $caseCheck) $fileCheck
            $hashCheck = (Get-FileHash -LiteralPath $pathCheck -Algorithm SHA256).Hash
            $documentCheck = $wordCheck.Documents.Open($pathCheck, $false, $true)
            $textCheck = [regex]::Replace($documentCheck.Content.Text.Replace([string][char]7, ' '), '\s+', ' ').Trim()
            $widthsCheck = @()
            if ($documentCheck.Tables.Count -gt 0) {
                foreach ($cellCheck in $documentCheck.Tables.Item(1).Rows.Item(1).Cells) {
                    $widthsCheck += [double]$cellCheck.Width
                }
            }
            $itemCheck = @{
                case=$caseCheck; file=$fileCheck; text=$textCheck;
                pages=[int]$documentCheck.ComputeStatistics(2); widths_points=$widthsCheck
            }
            $documentCheck.Close(0)
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documentCheck)
            $documentCheck = $null
            if ((Get-FileHash -LiteralPath $pathCheck -Algorithm SHA256).Hash -ne $hashCheck) {
                throw 'Word changed a read-only fixture'
            }
            if ($null -eq $baselineCheck) { $baselineCheck = $itemCheck }
            else {
                if ($itemCheck.text -ne $baselineCheck.text -or $itemCheck.pages -ne $baselineCheck.pages) {
                    throw "Word text/pages changed for $caseCheck/$fileCheck"
                }
                if ($itemCheck.widths_points.Count -ne $baselineCheck.widths_points.Count) {
                    throw 'Word column count changed'
                }
                for ($indexCheck=0; $indexCheck -lt $widthsCheck.Count; $indexCheck++) {
                    if ([math]::Abs($widthsCheck[$indexCheck] - $baselineCheck.widths_points[$indexCheck]) -gt 0.1) {
                        throw "Word column width changed for $caseCheck/$fileCheck"
                    }
                }
            }
            $observationsCheck += $itemCheck
        }
    }
    @{program='Microsoft Word'; version=$wordCheck.Version; build=$wordCheck.Build;
      success=$true; observations=$observationsCheck} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $documentCheck) { $documentCheck.Close(0) }
    if ($null -ne $wordCheck) {
        $wordCheck.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordCheck)
    }
}
