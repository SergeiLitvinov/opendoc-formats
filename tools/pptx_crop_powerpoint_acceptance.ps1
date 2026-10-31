param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('reference','render','outset')][string]$Stage='reference',
    [double]$OutsetLeftPt=-12
)

# Own picture from tests.writers.test_pptx_source_crop. Never activate external data.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null;$deck=$null;$shape=$null;$format=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $ownedProcess=Get-Process -Name POWERPNT
    $app.AutomationSecurity=3
    $app.DisplayAlerts=1
    $fileName=if($Stage -eq 'render'){'library.pptx'}else{'source.pptx'}
    $deck=$app.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        $shape=$deck.Slides.Item(1).Shapes.Item(1)
        $format=$shape.PictureFormat
        if($Stage -ne 'render'){
            $x=$shape.Left;$y=$shape.Top;$w=$shape.Width;$h=$shape.Height
            $shape.LockAspectRatio=0
            $format.CropLeft=if($Stage -eq 'outset'){$OutsetLeftPt}else{12}
            $format.CropTop=36
            $format.CropRight=12
            $format.CropBottom=18
            $shape.Width=$w;$shape.Height=$h;$shape.Left=$x;$shape.Top=$y
            $outputName=if($Stage -eq 'outset'){'outset.pptx'}else{'native.pptx'}
            $deck.SaveAs((Join-Path $nativeRoot $outputName),24)
        }
        $pdfName=if($Stage -eq 'render'){'library.pdf'}elseif($Stage -eq 'outset'){'outset.pdf'}else{'native.pdf'}
        $deck.SaveAs((Join-Path $nativeRoot $pdfName),32)
        [pscustomobject]@{
            version=$app.Version;stage=$Stage
            left=$shape.Left;top=$shape.Top;width=$shape.Width;height=$shape.Height
            crop_left=$format.CropLeft;crop_top=$format.CropTop
            source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $originalHash)
        }|ConvertTo-Json -Compress
    }finally{$deck.Close()}
}finally{
    if($null -ne $app){
        $app.Quit()
        foreach($item in @($format,$shape,$deck,$app)){
            if($null -ne $item){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($item)}
        }
        $format=$null;$shape=$null;$deck=$null;$app=$null;$item=$null
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
        if(-not $ownedProcess.WaitForExit(10000)){throw 'Owned PowerPoint has not exited; do not attach to it'}
    }
}
