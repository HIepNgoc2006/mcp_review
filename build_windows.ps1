$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Create project venv first: $Python" }
$env:PYTHONPATH = $Root
& $Python -m unittest discover -s (Join-Path $Root 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing to package.' }
& (Join-Path $Root '.venv\Scripts\pyinstaller.exe') --clean --noconfirm --onefile --console --name BridgeMCP --distpath (Join-Path $Root 'dist') --workpath (Join-Path $Root 'build') (Join-Path $Root 'mcp_server.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
& (Join-Path $Root 'dist\BridgeMCP.exe') --smoke-test
if ($LASTEXITCODE -ne 0) { throw 'Packaged MCP smoke test failed.' }
& $Python -m unittest discover -s (Join-Path $Root 'tests') -p test_packaged_mcp.py -v
if ($LASTEXITCODE -ne 0) { throw 'Packaged MCP stdio protocol tests failed.' }
certutil -hashfile (Join-Path $Root 'dist\BridgeMCP.exe') SHA256
