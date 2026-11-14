$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Create project venv first: $Python" }
$env:PYTHONPATH = $Root
& $Python -m unittest discover -s (Join-Path $Root 'tests') -p test_mcp_server.py -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing to package.' }
& (Join-Path $Root '.venv\Scripts\pyinstaller.exe') --clean --noconfirm --onefile --console --name BridgeMCP --distpath (Join-Path $Root 'dist') --workpath (Join-Path $Root 'build') (Join-Path $Root 'mcp_server.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
& (Join-Path $Root 'dist\BridgeMCP.exe') --smoke-test
if ($LASTEXITCODE -ne 0) { throw 'Packaged MCP smoke test failed.' }
Push-Location $Root
try {
    & $Python -c "import hashlib, zipfile; archive = zipfile.ZipFile('BridgeMCP-windows-x64.zip', 'w', zipfile.ZIP_DEFLATED); archive.write('dist/BridgeMCP.exe', 'BridgeMCP.exe'); archive.write('README.md', 'README.md'); archive.write('LICENSE', 'LICENSE'); archive.close(); print(hashlib.sha256(open('BridgeMCP-windows-x64.zip', 'rb').read()).hexdigest())" | Set-Content -Encoding ascii (Join-Path $Root 'SHA256SUMS.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Release archive creation failed.' }
}
finally {
    Pop-Location
}
& $Python -m unittest discover -s (Join-Path $Root 'tests') -p test_packaged_mcp.py -v
if ($LASTEXITCODE -ne 0) { throw 'Packaged MCP stdio and archive tests failed.' }
