$ErrorActionPreference = "Stop"

$pythonPath = "C:\cherry\venv\Scripts\python.exe"
$workFolder = "C:\Users\user\Desktop\prac"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $workFolder)) {
    throw "Notebook folder not found: $workFolder"
}

Set-Location -LiteralPath $workFolder
& $pythonPath -m jupyterlab
