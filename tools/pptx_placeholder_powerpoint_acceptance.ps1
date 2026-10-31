param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('reference','render')][string]$Stage='reference'
)

# Own title/body fixture; only the body receives a local frame override.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null;$deck=$null;$body=$null;$range=$null;$found=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $ownedProcess=Get-Process -Name POWERPNT
    $app.AutomationSecurity=3;$app.DisplayAlerts=1
    $fileName=if($Stage -eq 'reference'){'source.pptx'}else{'library.pptx'}
    $deck=$app.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        $body=$deck.Slides.Item(1).Shapes.Item(2)
        $before=@{left=$body.Left;top=$body.Top;width=$body.Width;height=$body.Height;rotation=$body.Rotation}
        if($Stage -eq 'reference'){
            $body.LockAspectRatio=0
            $body.Width=$body.Width-40;$body.Height=$body.Height-20
            $body.Rotation=$body.Rotation+9
            # Native size edits preserve a rotated center; set final frame origin last.
            $body.Left=$before.left+10;$body.Top=$before.top+5
            $range=$body.TextFrame.TextRange
            $found=$range.Find('Own inherited body')
            $found.Text='Own inherited edited'
            $deck.SaveAs((Join-Path $nativeRoot 'native.pptx'),24)
        }
        $pdfName=if($Stage -eq 'reference'){'native.pdf'}else{'library.pdf'}
        $deck.SaveAs((Join-Path $nativeRoot $pdfName),32)
        [pscustomobject]@{
            version=$app.Version;stage=$Stage;before=$before
            left=$body.Left;top=$body.Top;width=$body.Width;height=$body.Height;rotation=$body.Rotation
            source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $originalHash)
        }|ConvertTo-Json -Compress
    }finally{$deck.Close()}
}finally{
    if($null -ne $app){
        $app.Quit()
        foreach($item in @($found,$range,$body,$deck,$app)){
            if($null -ne $item){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($item)}
        }
        $found=$null;$range=$null;$body=$null;$deck=$null;$app=$null;$item=$null
        [GC]::Collect();[GC]::WaitForPendingFinalizers()
        if(-not $ownedProcess.WaitForExit(10000)){throw 'Owned PowerPoint has not exited; do not attach to it'}
    }
}
