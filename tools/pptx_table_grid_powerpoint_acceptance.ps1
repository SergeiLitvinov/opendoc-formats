param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('resize','redistribute')][string]$Profile='resize',
    [ValidateSet('reference','render')][string]$Stage='reference'
)

# Own 5x4 fixture from tests.writers.test_pptx_logical_grid.merged_source.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $app.AutomationSecurity=3
    $app.DisplayAlerts=1
    $fileName=if($Stage -eq 'reference'){'source.pptx'}else{'library.pptx'}
    $deck=$app.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        $shape=$deck.Slides.Item(1).Shapes.Item(1)
        if($Stage -eq 'reference'){
            if($Profile -eq 'resize'){
                $shape.LockAspectRatio=0
                $shape.Width=$shape.Width+100
                $shape.Height=$shape.Height+60
            }else{
                $shape.Table.Columns.Item(1).Width=$shape.Table.Columns.Item(1).Width+10
                $shape.Table.Columns.Item(2).Width=$shape.Table.Columns.Item(2).Width-10
                $shape.Table.Rows.Item(1).Height=$shape.Table.Rows.Item(1).Height+10
                $shape.Table.Rows.Item(2).Height=$shape.Table.Rows.Item(2).Height-10
            }
            $deck.SaveAs((Join-Path $nativeRoot 'native.pptx'),24)
        }
        $pdfName=if($Stage -eq 'reference'){'native.pdf'}else{'library.pdf'}
        $deck.SaveAs((Join-Path $nativeRoot $pdfName),32)
        [pscustomobject]@{
            version=$app.Version;profile=$Profile;stage=$Stage
            width=$shape.Width;height=$shape.Height
            source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $originalHash)
        }|ConvertTo-Json -Compress
    }finally{$deck.Close()}
}finally{
    if($null -ne $app){
        $app.Quit()
        if($null -ne $shape){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shape)}
        if($null -ne $deck){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
        $shape=$null;$deck=$null;$app=$null
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}
