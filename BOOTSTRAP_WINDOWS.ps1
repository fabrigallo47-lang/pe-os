$ErrorActionPreference = "Stop"
Write-Host "Installing PANTA dependencies..."
npm ci
Write-Host "Running full PANTA validation..."
npm run check:all
Write-Host "Ready. Start the synthetic product lab with: npm run lab"
