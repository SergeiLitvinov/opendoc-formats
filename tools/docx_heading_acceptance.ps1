param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
$headingWord = $null
$headingDocument = $null
try {
    $headingCases = @(Get-ChildItem -LiteralPath $FixtureRoot -Directory -Filter 'test_native_inheritance_direct*')
    if ($headingCases.Count -ne 1) {throw 'Expected one own heading fixture directory'}
    $headingWord = New-Object -ComObject Word.Application
    $headingWord.Visible = $false
    $headingWord.DisplayAlerts = 0
    $headingWord.AutomationSecurity = 3
    $headingObservations = @()
    foreach ($headingFile in @('source.docx','native-0.docx','native-1.docx')) {
        $headingPath = Join-Path $headingCases[0].FullName $headingFile
        $headingHash = (Get-FileHash -LiteralPath $headingPath -Algorithm SHA256).Hash
        $headingDocument = $headingWord.Documents.Open($headingPath, $false, $true)
        $headingLevels = @()
        foreach ($headingIndex in 1..5) {
            $headingLevels += [int]$headingDocument.Paragraphs.Item($headingIndex).OutlineLevel
        }
        if (($headingLevels -join ',') -ne '2,3,5,10,10') {throw "Word outline changed: $headingFile : $($headingLevels -join ',')"}
        $headingObservations += @{file=$headingFile;outline_levels=$headingLevels}
        $headingDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($headingDocument)
        $headingDocument = $null
        if ((Get-FileHash -LiteralPath $headingPath -Algorithm SHA256).Hash -ne $headingHash) {
            throw 'Word changed a read-only fixture'
        }
    }
    $headingEdits = @(Get-ChildItem -LiteralPath $FixtureRoot -Directory -Filter 'test_heading_edit_and_removal*')
    if ($headingEdits.Count -ne 1) {throw 'Expected one own heading edit directory'}
    $headingOriginalFormatting = $null
    foreach ($headingEditFile in @('input.docx','edited.docx','edited-1.docx')) {
        $headingEditPath = Join-Path $headingEdits[0].FullName $headingEditFile
        $headingEditHash = (Get-FileHash -LiteralPath $headingEditPath -Algorithm SHA256).Hash
        $headingDocument = $headingWord.Documents.Open($headingEditPath, $false, $true)
        if ($headingEditFile -ne 'input.docx') {
            $headingLevels = @([int]$headingDocument.Paragraphs.Item(1).OutlineLevel,
                              [int]$headingDocument.Paragraphs.Item(2).OutlineLevel)
            if (($headingLevels -join ',') -ne '7,10') {throw 'Word did not apply explicit role edit/removal'}
            $headingObservations += @{file=$headingEditFile;outline_levels=$headingLevels}
        }
        $headingFormatting = @()
        foreach ($headingIndex in 1..2) {
            $headingParagraph = $headingDocument.Paragraphs.Item($headingIndex)
            $headingFormatting += @{
                text=$headingParagraph.Range.Text; font_name=$headingParagraph.Range.Font.Name;
                font_size=$headingParagraph.Range.Font.Size; font_color=$headingParagraph.Range.Font.Color;
                space_before=$headingParagraph.SpaceBefore; space_after=$headingParagraph.SpaceAfter
            }
        }
        $headingDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($headingDocument)
        $headingDocument = $null
        if ((Get-FileHash -LiteralPath $headingEditPath -Algorithm SHA256).Hash -ne $headingEditHash) {
            throw 'Word changed a read-only fixture'
        }
        $headingFormattingJson = $headingFormatting | ConvertTo-Json -Depth 4 -Compress
        if ($null -eq $headingOriginalFormatting) {$headingOriginalFormatting = $headingFormattingJson}
        elseif ($headingOriginalFormatting -ne $headingFormattingJson) {
            throw "Heading role edit changed native text formatting: $headingOriginalFormatting -> $headingFormattingJson"
        }
    }
    @{program='Microsoft Word';version=$headingWord.Version;build=$headingWord.Build;
      success=$true;observations=$headingObservations} | ConvertTo-Json -Depth 5
}
finally {
    if ($null -ne $headingDocument) {$headingDocument.Close(0)}
    if ($null -ne $headingWord) {
        $headingWord.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($headingWord)
    }
}
