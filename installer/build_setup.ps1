$ErrorActionPreference = "Stop"

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $InstallerDir
$DistDir = Join-Path $ProjectDir "dist-py314"
$AppDir = Join-Path $DistDir "Resumator 11.4"
$PayloadDir = Join-Path $InstallerDir "payload"
$PayloadZip = Join-Path $PayloadDir "Resumator11.4-app.zip"
$SetupSpec = Join-Path $ProjectDir "build-spec\Resumator 11.4 Setup.spec"
$BuildDir = Join-Path $ProjectDir "build-setup"
$DownloadsDir = Join-Path $ProjectDir "downloads"
$DownloadSetup = Join-Path $DownloadsDir "Resumator_11.4_Setup.exe"
$BuildTools = Join-Path $ProjectDir "build-tools"
if (-not (Test-Path $BuildTools)) {
    $SiblingBuildTools = Join-Path (Split-Path -Parent $ProjectDir) "Resumator 6.2\build-tools"
    if (Test-Path $SiblingBuildTools) {
        $BuildTools = $SiblingBuildTools
    }
}
$PythonExe = "C:\Users\Leonardo\AppData\Local\Programs\Python\Python314\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

if (-not (Test-Path (Join-Path $AppDir "Resumator 11.4.exe"))) {
    throw "Aplicativo nao encontrado em $AppDir. Gere o app principal antes do instalador."
}

Copy-Item -LiteralPath (Join-Path $ProjectDir "README.txt") -Destination (Join-Path $AppDir "README.txt") -Force

New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $PayloadZip -Force
Copy-Item -LiteralPath (Join-Path $ProjectDir "data\prompts.json") -Destination $PayloadDir -Force
Copy-Item -LiteralPath (Join-Path $ProjectDir "README.txt") -Destination $PayloadDir -Force

$env:PYTHONPATH = $BuildTools
& $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $BuildDir $SetupSpec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falhou ao gerar o instalador."
}

$SetupExe = Join-Path $DistDir "Resumator 11.4 Setup.exe"
if (-not (Test-Path $SetupExe)) {
    throw "Instalador nao gerado em $SetupExe"
}

New-Item -ItemType Directory -Force -Path $DownloadsDir | Out-Null
Copy-Item -LiteralPath $SetupExe -Destination $DownloadSetup -Force

Write-Host "Instalador criado: $SetupExe"
Write-Host "Copia para download criada: $DownloadSetup"

