param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$themeWord = $null
$themeDocument = $null
try {
    $themeRoot = (Resolve-Path -LiteralPath $FixtureRoot).Path
    $workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $qaRoot = Join-Path $workspaceRoot '.opendoc-formats'
    if (-not $themeRoot.StartsWith($qaRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only own workspace QA fixtures are accepted'
    }
    $themeWord = New-Object -ComObject Word.Application
    $themeWord.Visible = $false
    $themeWord.DisplayAlerts = 0
    $themeWord.AutomationSecurity = 3
    $observations = @()
    foreach ($themeName in @('own.docx','cycle-0.docx','cycle-1.docx')) {
        $themePath = Join-Path $themeRoot $themeName
        $themeHash = (Get-FileHash -LiteralPath $themePath -Algorithm SHA256).Hash
        $themeDocument = $themeWord.Documents.Open($themePath, $false, $true)
        $themeRange = $themeDocument.Paragraphs.Item(1).Range
        $value = @{file=$themeName;family=$themeRange.Font.Name;size=$themeRange.Font.Size;
                   bold=$themeRange.Font.Bold;pages=$themeDocument.ComputeStatistics(2)}
        if ($value.family -ne 'Calibri' -or $value.size -ne 12 -or $value.bold -ne -1) {
            throw 'Own Calibri 12 bold effective font changed'
        }
        $observations += $value
        $themeDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($themeDocument)
        $themeDocument = $null
        if ((Get-FileHash -LiteralPath $themePath -Algorithm SHA256).Hash -ne $themeHash) {
            throw 'Read-only fixture changed'
        }
    }
    @{success=$true;program='Microsoft Word';version=$themeWord.Version;build=$themeWord.Build;
      observations=$observations} | ConvertTo-Json -Depth 5
}
finally {
    if ($null -ne $themeDocument) { $themeDocument.Close(0) }
    if ($null -ne $themeWord) {
        $themeWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($themeWord)
    }
}
