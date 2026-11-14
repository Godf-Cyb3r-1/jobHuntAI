# Requires Tailscale signed in on Windows and Android on the same tailnet.
# Run PowerShell; the command below provisions a stable tailnet-only HTTPS URL.
$ErrorActionPreference='Stop'
if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    throw 'Install and sign in to Tailscale on Windows first: https://tailscale.com/download/windows'
}
tailscale status | Out-Host
Write-Host 'Exposing JobHuntAI only inside your private Tailscale network...'
tailscale serve --bg 8765
tailscale serve status
Write-Host 'Install Tailscale on Android, sign into the same tailnet, and enter the displayed HTTPS URL in JobHuntAI.'
Write-Host 'The JobHuntAI pairing key is still required. This does NOT expose the app to the public internet.'
