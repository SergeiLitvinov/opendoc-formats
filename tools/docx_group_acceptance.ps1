param(
    [Parameter(Mandatory=$true)][string]$FixtureRoot,
    [string[]]$Names=@('source','cycle-0','cycle-1')
)
$ErrorActionPreference='Stop'
$formatRoot=(Resolve-Path -LiteralPath $FixtureRoot).Path
$formatAllowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.opendoc-formats'))
if(!$formatRoot.StartsWith($formatAllowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Only own workspace fixtures are accepted'
}
if($Names.Count -lt 2){throw 'Provide a native reference and at least one cycle'}
$formatWord=$null; $formatDocument=$null; $formatRecords=@()
try {
    $formatWord=New-Object -ComObject Word.Application
    $formatWord.Visible=$false; $formatWord.DisplayAlerts=0; $formatWord.AutomationSecurity=3
    foreach($formatName in $Names) {
        if($formatName -notmatch '^[a-zA-Z0-9-]+$'){throw 'Invalid fixture name'}
        $formatPath=Join-Path $formatRoot ($formatName+'.docx')
        $formatHash=(Get-FileHash -LiteralPath $formatPath).Hash
        $formatDocument=$formatWord.Documents.Open($formatPath,$false,$true)
        if($formatDocument.Shapes.Count -ne 1 -or $formatDocument.Shapes.Item(1).Type -ne 20) {
            throw 'Expected one independently editable drawing canvas'
        }
        $formatCanvas=$formatDocument.Shapes.Item(1)
        $formatGroups=@()
        for($formatIndex=1;$formatIndex -le $formatCanvas.CanvasItems.Count;$formatIndex++) {
            $formatGroup=$formatCanvas.CanvasItems.Item($formatIndex)
            if($formatGroup.Type -ne 6){continue}
            if($formatGroup.GroupItems.Count -ne 2){throw 'Expected two independently editable group children'}
            $formatChildren=@()
            for($formatChildIndex=1;$formatChildIndex -le 2;$formatChildIndex++) {
                $formatChild=$formatGroup.GroupItems.Item($formatChildIndex)
                $formatChildren+=[PSCustomObject]@{
                    name=$formatChild.Name;left=$formatChild.Left;top=$formatChild.Top
                    width=$formatChild.Width;height=$formatChild.Height
                    rgb=$formatChild.Fill.ForeColor.RGB;transparency=$formatChild.Fill.Transparency
                }
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatChild)
            }
            $formatGroups+=[PSCustomObject]@{
                name=$formatGroup.Name;left=$formatGroup.Left;top=$formatGroup.Top
                width=$formatGroup.Width;height=$formatGroup.Height;children=$formatChildren
            }
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatGroup)
        }
        if($formatGroups.Count -ne 1){throw 'Expected one logical group, not flattened child shapes'}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatCanvas)
        $formatDocument.ExportAsFixedFormat((Join-Path $formatRoot ($formatName+'.pdf')),17)
        $formatRecords+=[PSCustomObject]@{file=$formatName;groups=$formatGroups}
        $formatDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatDocument); $formatDocument=$null
        if((Get-FileHash -LiteralPath $formatPath).Hash -ne $formatHash){throw 'Word changed a read-only fixture'}
    }
    $formatExpected=$formatRecords[0].groups | ConvertTo-Json -Depth 8 -Compress
    foreach($formatRecord in $formatRecords[1..($formatRecords.Count-1)]) {
        if(($formatRecord.groups | ConvertTo-Json -Depth 8 -Compress) -ne $formatExpected) {
            throw 'Native group structure, geometry or child paints changed after a cycle'
        }
    }
    [PSCustomObject]@{
        program='Microsoft Word';version=$formatWord.Version;build=$formatWord.Build;files=$formatRecords
    } | ConvertTo-Json -Depth 10
} finally {
    try {
        if($formatDocument){$formatDocument.Close(0);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatDocument)}
    } finally {
        if($formatWord){$formatWord.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($formatWord)}
    }
}
