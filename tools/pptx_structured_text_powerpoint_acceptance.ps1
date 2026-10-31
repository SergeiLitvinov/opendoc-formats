param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('reference','render')][string]$Stage='reference'
)

# Own shape/table fixture. Only surrounding ordinary text is replaced, never fields.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$nativeRoot=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $nativeRoot 'source.pptx'
$originalHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null;$deck=$null;$owner=$null;$range=$null;$found=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $ownedProcess=Get-Process -Name POWERPNT
    $app.AutomationSecurity=3
    $app.DisplayAlerts=1
    $fileName=if($Stage -eq 'reference'){'source.pptx'}else{'library.pptx'}
    $deck=$app.Presentations.Open((Join-Path $nativeRoot $fileName),-1,0,0)
    try {
        $owner=$deck.Slides.Item(1).Shapes.Item(1)
        $range=if($owner.HasTable){$owner.Table.Cell(1,1).Shape.TextFrame.TextRange}else{$owner.TextFrame.TextRange}
        if($Stage -eq 'reference'){
            foreach($pair in @(@('Before ','Before edited '),@(' After',' After edited'),@('Tail','Tail edited'))){
                $found=$range.Find($pair[0])
                if($null -eq $found){throw 'Own target text not found'}
                $found.Text=$pair[1]
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($found)
                $found=$null
            }
            $deck.SaveAs((Join-Path $nativeRoot 'native.pptx'),24)
        }
        $pdfName=if($Stage -eq 'reference'){'native.pdf'}else{'library.pdf'}
        $deck.SaveAs((Join-Path $nativeRoot $pdfName),32)
        [pscustomobject]@{
            version=$app.Version;stage=$Stage
            source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $originalHash)
        }|ConvertTo-Json -Compress
    }finally{$deck.Close()}
}finally{
    if($null -ne $app){
        $app.Quit()
        foreach($item in @($found,$range,$owner,$deck,$app)){
            if($null -ne $item){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($item)}
        }
        $found=$null;$range=$null;$owner=$null;$deck=$null;$app=$null;$item=$null
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
        if(-not $ownedProcess.WaitForExit(10000)){throw 'Owned PowerPoint has not exited; do not attach to it'}
    }
}
