param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('reference','render')][string]$Stage='reference'
)

# Own classic-chart fixture from tests.writers.test_pptx_source_chart_frame.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null;$deck=$null;$shape=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $ownedProcess=Get-Process -Name POWERPNT
    $app.AutomationSecurity=3
    $app.DisplayAlerts=1
    $fileName=if($Stage -eq 'reference'){'source.pptx'}else{'library.pptx'}
    $deck=$app.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        $shape=$deck.Slides.Item(1).Shapes.Item(1)
        if($Stage -eq 'reference'){
            $shape.LockAspectRatio=0
            $shape.Left=$shape.Left+10
            $shape.Top=$shape.Top+5
            $shape.Width=$shape.Width+120
            $shape.Height=$shape.Height+60
            $deck.SaveAs((Join-Path $nativeRoot 'native.pptx'),24)
        }
        $pdfName=if($Stage -eq 'reference'){'native.pdf'}else{'library.pdf'}
        $deck.SaveAs((Join-Path $nativeRoot $pdfName),32)
        [pscustomobject]@{
            version=$app.Version;stage=$Stage
            left=$shape.Left;top=$shape.Top;width=$shape.Width;height=$shape.Height
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
        if(-not $ownedProcess.WaitForExit(10000)){throw 'Owned PowerPoint has not exited; do not attach to it'}
    }
}
