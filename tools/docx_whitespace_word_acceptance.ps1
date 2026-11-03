param([Parameter(Mandatory=$true)][string]$FixtureRoot, [switch]$PdfA, [switch]$PageGeometry)
$ErrorActionPreference = 'Stop'
if (-not ('DocxWhitespaceNative' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DocxWhitespaceNative {
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@
}
$fixturePath = [IO.Path]::GetFullPath($FixtureRoot)
$manifest = Get-Content -LiteralPath (Join-Path $fixturePath 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$outputPath = Join-Path $fixturePath $(if ($PdfA) { 'native-pdfa' } else { 'native' })
if (Test-Path -LiteralPath $outputPath) { throw 'Native output already exists' }
$previousWordIds = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$word = $null; $documents = $null; $document = $null; $range = $null; $window = $null
$nativeSections = $null; $nativeSection = $null; $pageSetup = $null
$ownedWord = $false; $wordProcess = $null; $results = @()
try {
    $word = New-Object -ComObject Word.Application
    # Word is a documented SingleUse automation server: CreateObject owns a new
    # application. Verify its process through the first private document window.
    $ownedWord = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $documents = $word.Documents
    [void](New-Item -ItemType Directory -Path $outputPath)
    foreach ($case in $manifest) {
        if ([IO.Path]::GetFileName([string]$case.file) -ne $case.file -or [IO.Path]::GetExtension($case.file) -ne '.docx') {
            throw 'Fixture manifest contains an unsafe filename'
        }
        $path = Join-Path $fixturePath $case.file
        $pdf = Join-Path $outputPath ([IO.Path]::GetFileNameWithoutExtension($case.file)+'.pdf')
        if (Test-Path -LiteralPath $pdf) { throw 'Native PDF output already exists' }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        $document = $documents.Open($path, $false, $true, $false)
        $window = $document.ActiveWindow
        [uint32]$nativeProcessId = 0
        [void][DocxWhitespaceNative]::GetWindowThreadProcessId([IntPtr]$window.Hwnd, [ref]$nativeProcessId)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($window); $window = $null
        if ($nativeProcessId -eq 0 -or $previousWordIds -contains [int]$nativeProcessId) {
            $ownedWord = $false
            throw 'Automation did not create a distinct owned Word process'
        }
        if ($null -eq $wordProcess) { $wordProcess = Get-Process -Id $nativeProcessId }
        if ($wordProcess.Id -ne $nativeProcessId) { throw 'Word changed process during acceptance' }
        $range = $document.Content
        $text = [string]$range.Text
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($range); $range = $null
        $geometry = @()
        if ($PageGeometry) {
            $nativeSections = $document.Sections
            for ($sectionIndex = 1; $sectionIndex -le $nativeSections.Count; $sectionIndex++) {
                $nativeSection = $nativeSections.Item($sectionIndex)
                $pageSetup = $nativeSection.PageSetup
                $geometry += @{width=[double]$pageSetup.PageWidth; height=[double]$pageSetup.PageHeight;
                               top=[double]$pageSetup.TopMargin; right=[double]$pageSetup.RightMargin;
                               bottom=[double]$pageSetup.BottomMargin; left=[double]$pageSetup.LeftMargin;
                               header=[double]$pageSetup.HeaderDistance; footer=[double]$pageSetup.FooterDistance;
                               gutter=[double]$pageSetup.Gutter; orientation=[int]$pageSetup.Orientation}
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($pageSetup); $pageSetup = $null
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nativeSection); $nativeSection = $null
            }
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nativeSections); $nativeSections = $null
        }
        if ($PdfA) {
            $document.ExportAsFixedFormat($pdf, 17, $false, 0, 0, 1, 1, 0, $false, $false, 0, $true, $true, $true)
        } else {
            $document.ExportAsFixedFormat($pdf, 17)
        }
        $observation = @{name=$case.name; file=$case.file; sha256=$hash; text=$text;
                         compatibility_mode=[int]$document.CompatibilityMode; pages=[int]$document.ComputeStatistics(2)}
        if ($PageGeometry) { $observation.page_geometry = $geometry }
        $results += $observation
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document); $document = $null
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $hash) { throw 'Read-only source changed' }
    }
    @{program='Microsoft Word'; version=$word.Version; build=$word.Build; process_id=$nativeProcessId;
      pdf_profile=$(if ($PdfA) { 'Word PDF/A-1 export' } else { 'Word standard PDF export' });
      distinct_owned_process=$true; observations=$results} | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $outputPath 'observations.json') -Encoding UTF8
}
finally {
    if ($null -ne $pageSetup) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($pageSetup) }
    if ($null -ne $nativeSection) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nativeSection) }
    if ($null -ne $nativeSections) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nativeSections) }
    if ($null -ne $window) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($window) }
    if ($null -ne $range) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($range) }
    if ($null -ne $document) {
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $documents) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documents) }
    if ($null -ne $word) {
        if ($ownedWord) { $word.Quit() }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    if ($null -ne $wordProcess -and $ownedWord -and -not $wordProcess.WaitForExit(10000)) {
        throw 'Owned Word process has not exited; no process was killed'
    }
}
Get-Content -LiteralPath (Join-Path $outputPath 'observations.json') -Raw -Encoding UTF8
