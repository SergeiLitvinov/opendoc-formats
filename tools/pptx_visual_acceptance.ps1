param([Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference='Stop'
$pptCheck=$null
$deckCheck=$null
$rootCheck=[IO.Path]::GetFullPath($FixtureRoot)
$recordsCheck=@()
try {
    $pptCheck=New-Object -ComObject PowerPoint.Application
    $pptCheck.AutomationSecurity=3
    foreach ($caseCheck in @('test_effective_solid_backgroun0','test_effective_solid_backgroun1',
                            'test_effective_solid_backgroun2','test_freeform_axis_lines_two_j0','test_table_theme_audit0')) {
        $baselineCheck=$null
        foreach ($fileCheck in @('source.pptx','cycle-0.pptx','cycle-1.pptx')) {
            $pathCheck=Join-Path (Join-Path $rootCheck $caseCheck) $fileCheck
            $hashCheck=(Get-FileHash -LiteralPath $pathCheck -Algorithm SHA256).Hash
            $deckCheck=$pptCheck.Presentations.Open($pathCheck,-1,0,0)
            $slideCheck=$deckCheck.Slides.Item(1)
            $shapesCheck=@()
            $cellsCheck=@()
            foreach ($shapeCheck in $slideCheck.Shapes) {
                $shapesCheck+=@{type=[int]$shapeCheck.Type;left=[double]$shapeCheck.Left;top=[double]$shapeCheck.Top;
                              width=[double]$shapeCheck.Width;height=[double]$shapeCheck.Height}
                if ($shapeCheck.HasTable -eq -1) {
                    foreach ($rowCheck in 1..$shapeCheck.Table.Rows.Count) {
                        foreach ($columnCheck in 1..$shapeCheck.Table.Columns.Count) {
                            $cellCheck=$shapeCheck.Table.Cell($rowCheck,$columnCheck).Shape
                            $cellsCheck+=@{row=$rowCheck;column=$columnCheck;
                                          text=$cellCheck.TextFrame.TextRange.Text;
                                          rgb=[int]$cellCheck.TextFrame.TextRange.Font.Color.RGB}
                        }
                    }
                }
            }
            $itemCheck=@{case=$caseCheck;file=$fileCheck;shapes=$shapesCheck;cells=$cellsCheck;
                         background_rgb=[int]$slideCheck.Background.Fill.ForeColor.RGB}
            $signatureCheck=@{shapes=$shapesCheck;cells=$cellsCheck;background_rgb=$itemCheck.background_rgb} |
                            ConvertTo-Json -Depth 6 -Compress
            if ($null -eq $baselineCheck) { $baselineCheck=$signatureCheck }
            elseif ($signatureCheck -ne $baselineCheck) { throw "PowerPoint properties changed for $caseCheck/$fileCheck" }
            $recordsCheck+=$itemCheck
            $deckCheck.Close()
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deckCheck)
            $deckCheck=$null
            if ((Get-FileHash -LiteralPath $pathCheck -Algorithm SHA256).Hash -ne $hashCheck) { throw 'Input changed' }
        }
    }
    @{program='Microsoft PowerPoint';version=$pptCheck.Version;build=$pptCheck.Build;success=$true;
      observations=$recordsCheck} | ConvertTo-Json -Depth 7
}
finally {
    if ($null -ne $deckCheck) { $deckCheck.Close() }
    if ($null -ne $pptCheck) {
        $pptCheck.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($pptCheck)
    }
}
