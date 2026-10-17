param([Parameter(Mandatory=$true)][string]$FixtureRoot, [switch]$NativeEdit)
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
        $document.Styles.Item('Own Indent Base').ParagraphFormat.LeftIndent=50
        $document.Styles.Item('Own Indent Base').ParagraphFormat.RightIndent=24.05
        $document.Styles.Item('Own Indent Base').ParagraphFormat.FirstLineIndent=-6.05
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
        $indents=@()
        foreach ($index in 1..3) {
            $format=$document.Paragraphs.Item($index).Format
            $indents+=,@($format.LeftIndent,$format.RightIndent,$format.FirstLineIndent)
        }
        $expected=@(@(30,18,12),@(48,24,-12),@(0,0,0))
        if ($file.Name -match 'defaulted') { $expected[0]=@(6,3,0) }
        elseif ($file.Name -match 'style-deleted') { $expected[0]=@(0,0,0) }
        elseif ($file.Name -match 'deleted') { $expected[0]=@(50,24.05,-6.05);$expected[1]=@(50,24.05,-6.05) }
        elseif ($file.Name -match 'edit') { $expected[0]=@(50,24.05,-6.05) }
        for ($paragraphIndex=0;$paragraphIndex -lt 3;$paragraphIndex++) {
            for ($axis=0;$axis -lt 3;$axis++) {
                if ([Math]::Abs($indents[$paragraphIndex][$axis]-$expected[$paragraphIndex][$axis]) -gt 0.01) {
                    throw "Word indent mismatch: $($file.Name), paragraph $paragraphIndex, axis $axis"
                }
            }
        }
        $document.ExportAsFixedFormat(($file.FullName+'.pdf'),17)
        $observations+=@{file=$file.Name;pages=$document.ComputeStatistics(2);indents=$indents}
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
