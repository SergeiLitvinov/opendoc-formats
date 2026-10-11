param([Parameter(Mandatory=$true)][string]$FixtureRoot, [switch]$VerifyFinal)
$ErrorActionPreference = 'Stop'
$layoutWord = $null
$layoutDocument = $null
$layoutObservations = @()
try {
    $layoutRoot = (Resolve-Path -LiteralPath $FixtureRoot).Path
    $layoutAllowed = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.opendoc-formats'))
    if (!$layoutRoot.StartsWith($layoutAllowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only own workspace QA fixtures are accepted'
    }
    $layoutWord = New-Object -ComObject Word.Application
    $layoutWord.Visible = $false
    $layoutWord.DisplayAlerts = 0
    $layoutWord.AutomationSecurity = 3
    $layoutNames = if ($VerifyFinal) { @('native-cycle.docx') } else {
        @('source.docx','cycle-0.docx','cycle-1.docx','edited.docx','deleted.docx')
    }
    foreach ($layoutName in $layoutNames) {
        $layoutPath = Join-Path $layoutRoot $layoutName
        $layoutHash = (Get-FileHash -LiteralPath $layoutPath -Algorithm SHA256).Hash
        $layoutDocument = $layoutWord.Documents.Open($layoutPath, $false, $true)
        $layoutIndent = $layoutDocument.Tables.Item(1).Rows.LeftIndent
        $layoutTabs = $layoutDocument.Paragraphs.Item(1).TabStops
        $layoutCustomTabs = @()
        if ($layoutTabs.Count -gt 0) {
            foreach ($layoutIndex in 1..$layoutTabs.Count) {
                $layoutCandidate = $layoutTabs.Item($layoutIndex)
                if ($layoutCandidate.CustomTab) { $layoutCustomTabs += $layoutCandidate }
            }
        }
        $layoutExpected = if ($VerifyFinal) { @(12,296,1,1) } elseif ($layoutName -eq 'edited.docx') {
            @(-6.05,72.05,3,1)
        } elseif ($layoutName -eq 'deleted.docx') { @(0) } else { @(30,396,2,3) }
        if ([Math]::Abs($layoutIndent-$layoutExpected[0]) -gt 0.01) { throw 'Word table indentation mismatch' }
        $layoutTabValues = @()
        if ($layoutExpected.Count -gt 1) {
            # Word can expose a near-default rounded alias in this collection.
            # The source OOXML inventory separately verifies actual declaration count.
            $layoutDeclared = @($layoutCustomTabs | Where-Object {
                [Math]::Abs($_.Position-$layoutExpected[1]) -le 0.01
            })
            if ($layoutDeclared.Count -ne 1) {
                throw "Word declared tab missing or ambiguous: $layoutName"
            }
            $layoutTab = $layoutDeclared[0]
            if ([Math]::Abs($layoutTab.Position-$layoutExpected[1]) -gt 0.01 -or
                $layoutTab.Alignment -ne $layoutExpected[2] -or $layoutTab.Leader -ne $layoutExpected[3]) {
                throw 'Word tab position/alignment/leader mismatch'
            }
            $layoutTabValues += @{position=$layoutTab.Position;alignment=$layoutTab.Alignment;leader=$layoutTab.Leader}
        } elseif ($layoutCustomTabs.Count -ne 0) { throw 'Deleted tabs returned' }
        $layoutDocument.ExportAsFixedFormat((Join-Path $layoutRoot ($layoutName+'.pdf')),17)
        $layoutObservations += @{file=$layoutName;indent=$layoutIndent;tabs=$layoutTabValues;
            pages=$layoutDocument.ComputeStatistics(2)}
        $layoutDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($layoutDocument)
        $layoutDocument = $null
        if ((Get-FileHash -LiteralPath $layoutPath -Algorithm SHA256).Hash -ne $layoutHash) { throw 'Source changed' }
    }
    if (!$VerifyFinal) {
        $layoutEdit = Join-Path $layoutRoot 'native-edit.docx'
        Copy-Item -LiteralPath (Join-Path $layoutRoot 'cycle-1.docx') -Destination $layoutEdit
        $layoutDocument = $layoutWord.Documents.Open($layoutEdit,$false,$false)
        $layoutDocument.Tables.Item(1).Rows.LeftIndent = 12
        $layoutTabs = $layoutDocument.Paragraphs.Item(1).TabStops
        $layoutTabs.ClearAll()
        [void]$layoutTabs.Add(296,1,1)
        $layoutDocument.Save()
        $layoutDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($layoutDocument)
        $layoutDocument = $null
    }
    @{success=$true;program='Microsoft Word';version=$layoutWord.Version;build=$layoutWord.Build;
        observations=$layoutObservations} | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $layoutDocument) { $layoutDocument.Close(0) }
    if ($null -ne $layoutWord) {
        $layoutWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($layoutWord)
    }
}
