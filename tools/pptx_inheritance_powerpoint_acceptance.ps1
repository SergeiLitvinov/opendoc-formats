param([Parameter(Mandatory=$true)][string]$Root,[ValidateSet('render','edit')][string]$Stage='render')
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running; never attach to an existing instance'}
$rootPath=(Resolve-Path -LiteralPath $Root).Path
$manifest=Get-Content -LiteralPath (Join-Path $rootPath 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$app=$null;$deck=$null;$owned=$false;$process=$null;$results=@()
try{
 $started=Get-Date
 $app=New-Object -ComObject PowerPoint.Application
 $app.AutomationSecurity=3;$app.DisplayAlerts=1
 $created=@(Get-Process -Name POWERPNT -ErrorAction Stop)
 if($created.Count -ne 1 -or $created[0].StartTime -lt $started.AddSeconds(-2)){
  throw 'Cannot prove a newly created, exclusive PowerPoint process'
 }
 $process=$created[0]
 $owned=$true
 $files=$manifest.files
 if($Stage -eq 'edit'){
  $sourcePath=Join-Path $rootPath 'visible/own-inheritance.pptx'
  $sourceHash=(Get-FileHash -LiteralPath $sourcePath).Hash
  $referencePdf=Join-Path $rootPath 'visible/native-edit.pdf'
  if(Test-Path -LiteralPath $referencePdf){throw 'Native edit reference already exists'}
  $deck=$app.Presentations.Open($sourcePath,-1,0,0)
  $shape=$null
  try{
   $shape=$deck.SlideMaster.Shapes.Item('Own inherited square')
   $shape.LockAspectRatio=0
   $shape.Left=$shape.Left+10
   $shape.Width=$shape.Width+5
   $deck.SaveAs($referencePdf,32)
   $results += [pscustomobject]@{file='visible/own-inheritance.pptx';source_sha256=$sourceHash;pages=$deck.Slides.Count;source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $sourceHash);left=$shape.Left;width=$shape.Width}
  }finally{
   $deck.Close()
   if($null -ne $shape){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shape)}
   [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck);$shape=$null;$deck=$null
  }
  $files=@([pscustomobject]@{file='visible/edited-1.pptx'},[pscustomobject]@{file='visible/edited-2.pptx'})
 }
 foreach($item in $files){
  $inputPath=[IO.Path]::GetFullPath((Join-Path $rootPath $item.file))
  if(-not $inputPath.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Input outside QA root'}
  $outputPath=[IO.Path]::ChangeExtension($inputPath,'.pdf')
  if(Test-Path -LiteralPath $outputPath){throw 'Native output already exists'}
  $before=(Get-FileHash -LiteralPath $inputPath).Hash
  $deck=$app.Presentations.Open($inputPath,-1,0,0)
  try{
   $deck.SaveAs($outputPath,32)
   $results += [pscustomobject]@{file=$item.file;source_sha256=$before;pages=$deck.Slides.Count;source_unchanged=((Get-FileHash -LiteralPath $inputPath).Hash -eq $before)}
  }finally{
   $deck.Close();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck);$deck=$null
  }
 }
 $resultName=if($Stage -eq 'render'){'native.json'}else{'native-edit.json'}
 [pscustomobject]@{version=$app.Version;stage=$Stage;files=$results;success=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $rootPath $resultName) -Encoding UTF8
}finally{
 if($owned -and $null -ne $app){$app.Quit()}
 if($null -ne $app){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)}
 $app=$null;[GC]::Collect();[GC]::WaitForPendingFinalizers()
 if($owned -and -not $process.WaitForExit(10000)){throw 'Owned PowerPoint has not exited'}
}
