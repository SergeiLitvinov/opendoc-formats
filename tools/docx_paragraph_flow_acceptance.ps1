param([Parameter(Mandatory=$true)][string]$FixtureRoot, [switch]$NativeEdit, [switch]$ObserveOnly)
$ErrorActionPreference='Stop'
$fixtureRoot=(Resolve-Path -LiteralPath $FixtureRoot).Path
$allowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.opendoc-formats'))
if (-not $fixtureRoot.StartsWith($allowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Only own workspace QA fixtures are accepted'
}
$word=$null
$document=$null
try {
    $word=New-Object -ComObject Word.Application
    $word.Visible=$false
    $word.DisplayAlerts=0
    $word.AutomationSecurity=3
    if ($NativeEdit) {
        $edit=Join-Path $fixtureRoot 'native-edit.docx'
        Copy-Item -LiteralPath (Join-Path $fixtureRoot 'source.docx') -Destination $edit
        $document=$word.Documents.Open($edit,$false,$false)
        $format=$document.Styles.Item('Own Flow Base').ParagraphFormat
        $format.SpaceBefore=22.05
        $format.SpaceAfter=32.05
        $format.KeepTogether=-1
        $format.KeepWithNext=-1
        $format.PageBreakBefore=-1
        $format.WidowControl=0
        # Word can normalize direct flags equal to the previous style value.
        # Reassert the independent reference's intended explicit overrides.
        foreach ($index in 2..3) {
            $direct=$document.Paragraphs.Item($index).Format
            $direct.KeepTogether=0
            $direct.KeepWithNext=0
            $direct.PageBreakBefore=0
            $direct.WidowControl=0
        }
        $document.Save()
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        $document=$null
        $deleted=Join-Path $fixtureRoot 'native-deleted.docx'
        Copy-Item -LiteralPath $edit -Destination $deleted
        $document=$word.Documents.Open($deleted,$false,$false)
        $document.Paragraphs.Item(2).Format.Reset()
        $document.Save()
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        $document=$null
    }
    $observations=@()
    foreach ($file in @(Get-ChildItem -LiteralPath $fixtureRoot -Filter '*.docx')) {
        $hash=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        $document=$word.Documents.Open($file.FullName,$false,$true)
        $values=@()
        foreach ($index in 1..3) {
            $format=$document.Paragraphs.Item($index).Format
            $values+=,@($format.SpaceBefore,$format.SpaceAfter,$format.KeepTogether,$format.KeepWithNext,
                         $format.PageBreakBefore,$format.WidowControl)
        }
        $expected=@(@(14,8,0,0,0,-1),@(20,20,0,0,0,0),@(0,0,0,0,0,0))
        if ($file.Name -match 'edit|deleted') { $expected[0]=@(22.05,32.05,-1,-1,-1,0) }
        if ($file.Name -match 'deleted') { $expected[1]=@(22.05,32.05,-1,-1,-1,0) }
        if ($file.Name -match 'defaulted') { $expected[0]=@(6,6,0,0,0,0) }
        if ($file.Name -match 'removed') { $expected[0]=@(0,0,0,0,0,-1) }
        if (-not $ObserveOnly) {
            for ($paragraphIndex=0;$paragraphIndex -lt 3;$paragraphIndex++) {
                for ($axis=0;$axis -lt 6;$axis++) {
                    if ([Math]::Abs($values[$paragraphIndex][$axis]-$expected[$paragraphIndex][$axis]) -gt 0.01) {
                        throw "Word flow mismatch: $($file.Name), paragraph $paragraphIndex, axis $axis"
                    }
                }
            }
        }
        $document.ExportAsFixedFormat(($file.FullName+'.pdf'),17)
        $observations+=@{file=$file.Name;pages=$document.ComputeStatistics(2);flow=$values}
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        $document=$null
        if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $hash) { throw 'Source changed' }
    }
    @{version=$word.Version;build=$word.Build;observations=$observations} | ConvertTo-Json -Depth 6
} finally {
    if ($null -ne $document) {$document.Close(0)}
    if ($null -ne $word) {$word.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)}
}
