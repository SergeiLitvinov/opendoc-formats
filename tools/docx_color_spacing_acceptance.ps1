param([Parameter(Mandatory=$true)][string]$FixtureRoot,[switch]$VerifyFinal)
$ErrorActionPreference='Stop'
$formatWord=$null
$formatDocument=$null
$formatRoot=(Resolve-Path -LiteralPath $FixtureRoot).Path
$formatAllowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.opendoc-formats'))
if(!$formatRoot.StartsWith($formatAllowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Only own workspace fixtures are accepted'
}
$formatRecords=@()
try {
    $formatWord=New-Object -ComObject Word.Application
    $formatWord.Visible=$false
    $formatWord.DisplayAlerts=0
    $formatWord.AutomationSecurity=3
    $formatNames=if($VerifyFinal){@('native-edit.docx','native-cycle.docx')}else{
        @('source.docx','cycle-0.docx','cycle-1.docx','edited.docx','deleted.docx')
    }
    foreach($formatName in $formatNames) {
        $formatPath=Join-Path $formatRoot $formatName
        $formatHash=(Get-FileHash -LiteralPath $formatPath).Hash
        $formatDocument=$formatWord.Documents.Open($formatPath,$false,$true)
        $formatParagraphs=@()
        for($formatIndex=1;$formatIndex -le 6;$formatIndex++) {
            $formatParagraph=$formatDocument.Paragraphs.Item($formatIndex)
            $formatRange=$formatParagraph.Range.Duplicate
            $formatRange.End=$formatRange.End-1
            $formatParagraphs+=[PSCustomObject]@{
                color=$formatRange.Font.Color
                rule=$formatParagraph.Format.LineSpacingRule
                spacing=$formatParagraph.Format.LineSpacing
            }
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatRange)
        }
        $formatDocument.ExportAsFixedFormat((Join-Path $formatRoot ($formatName+'.pdf')),17)
        $formatPages=$formatDocument.ComputeStatistics(2)
        $formatDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatDocument)
        $formatDocument=$null
        if((Get-FileHash -LiteralPath $formatPath).Hash -ne $formatHash){throw 'Word changed read-only fixture'}
        $formatRecords+=[PSCustomObject]@{file=$formatName;pages=$formatPages;paragraphs=$formatParagraphs}
    }
    if(!$VerifyFinal) {
        $formatOriginal=$formatRecords[0]
        foreach($formatRecord in $formatRecords[1..2]) {
            if(($formatRecord.paragraphs | ConvertTo-Json -Compress) -ne ($formatOriginal.paragraphs | ConvertTo-Json -Compress) -or
                $formatRecord.pages -ne $formatOriginal.pages){throw 'Source native formatting differs after cycle'}
        }
        if($formatOriginal.paragraphs[2].rule -ne 3 -or $formatOriginal.paragraphs[2].spacing -ne 14){throw 'Minimum source mismatch'}
        if($formatOriginal.paragraphs[3].rule -ne 4 -or $formatOriginal.paragraphs[3].spacing -ne 14){throw 'Exact source mismatch'}
        if($formatRecords[3].paragraphs[0].color -ne 0x563412 -or
            $formatRecords[3].paragraphs[2].rule -ne 4 -or $formatRecords[3].paragraphs[2].spacing -ne 18){throw 'Model edit mismatch'}
        if($formatRecords[4].paragraphs[0].color -ne $formatOriginal.paragraphs[1].color){throw 'Removed auto did not inherit heading color'}
        $formatNative=Join-Path $formatRoot 'native-edit.docx'
        Copy-Item -LiteralPath (Join-Path $formatRoot 'source.docx') -Destination $formatNative
        $formatDocument=$formatWord.Documents.Open($formatNative,$false,$false)
        $formatRange=$formatDocument.Paragraphs.Item(1).Range.Duplicate
        $formatRange.End=$formatRange.End-1
        $formatRange.Font.Color=0x563412
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatRange)
        $formatDocument.Paragraphs.Item(3).Format.LineSpacingRule=4
        $formatDocument.Paragraphs.Item(3).Format.LineSpacing=18
        $formatDocument.Save()
        $formatDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatDocument)
        $formatDocument=$null
    } else {
        if($formatRecords[0].paragraphs[0].color -ne 0x563412 -or
            $formatRecords[0].paragraphs[2].rule -ne 4 -or $formatRecords[0].paragraphs[2].spacing -ne 18){throw 'Native edit lost after public cycle'}
        if(($formatRecords[0].paragraphs | ConvertTo-Json -Compress) -ne ($formatRecords[1].paragraphs | ConvertTo-Json -Compress) -or
            $formatRecords[0].pages -ne $formatRecords[1].pages){throw 'Native edit snapshot differs after public cycle'}
    }
    [PSCustomObject]@{program='Microsoft Word';version=$formatWord.Version;build=$formatWord.Build;files=$formatRecords} | ConvertTo-Json -Depth 6
} finally {
    if($formatDocument -ne $null){$formatDocument.Close(0);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatDocument)}
    if($formatWord -ne $null){$formatWord.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatWord)}
}
