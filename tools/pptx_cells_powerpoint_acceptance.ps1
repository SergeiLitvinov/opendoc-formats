param([Parameter(Mandatory=$true)][string]$Root)

# Own fixture from tests.writers.test_pptx_source_cells. Macro execution disabled;
# native reference edits and library rendering use a fresh, read-only session.
$ErrorActionPreference='Stop'
if(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue){throw 'PowerPoint already running'}
$rootPath=(Resolve-Path -LiteralPath $Root).Path
$sourcePath=Join-Path $rootPath 'table.pptx'
$sourceHash=(Get-FileHash -LiteralPath $sourcePath).Hash
$app=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $app.AutomationSecurity=3
    $app.DisplayAlerts=1
    $deck=$app.Presentations.Open($sourcePath,-1,0,0)
    try {
        $table=$deck.Slides.Item(1).Shapes.Item(1).Table
        $table.Cell(1,1).Shape.TextFrame.TextRange.Text='Merged edit 0'
        $table.Cell(1,3).Shape.TextFrame.TextRange.Paragraphs(1).Runs(1).Text='Bold edit'
        $table.Cell(3,3).Shape.TextFrame.TextRange.Text='New cell 0'
        $deck.SaveAs((Join-Path $rootPath 'native.pptx'),24)
        $deck.SaveAs((Join-Path $rootPath 'native.pdf'),32)
    }finally{$deck.Close()}
    $deck=$app.Presentations.Open((Join-Path $rootPath 'library.pptx'),-1,0,0)
    try{
        $table=$deck.Slides.Item(1).Shapes.Item(1).Table
        $deck.SaveAs((Join-Path $rootPath 'library.pdf'),32)
        [pscustomobject]@{
            version=$app.Version
            empty_size=$table.Cell(3,3).Shape.TextFrame.TextRange.Font.Size
            source_unchanged=((Get-FileHash -LiteralPath $sourcePath).Hash -eq $sourceHash)
        }|ConvertTo-Json -Compress
    }finally{$deck.Close()}
}finally{if($null -ne $app){$app.Quit()}}
