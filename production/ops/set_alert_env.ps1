param(
    [string]$NtfyTopic = "",
    [string]$NtfyUrl = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ntfy.sh only (2026-09-08 decision). Telegram / webhook / Twilio senders were
# deleted from send_morning_alert.py and build_automation_self_check.py, so
# this script no longer sets those variables.

Write-Host "Setting user-level alert environment variables..."
if ($NtfyTopic) {
    [Environment]::SetEnvironmentVariable("NTFY_TOPIC", $NtfyTopic, "User")
}
if ($NtfyUrl) {
    [Environment]::SetEnvironmentVariable("NTFY_URL", $NtfyUrl, "User")
}

Write-Host "Done."
Write-Host "Alerts go to ntfy.sh via NTFY_TOPIC (or NTFY_URL)."
