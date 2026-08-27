param(
    [string]$AlertToNumber = "+19194497024",
    [string]$NtfyTopic = "",
    [string]$NtfyUrl = "",
    [string]$TelegramBotToken = "",
    [string]$TelegramChatId = "",
    [string]$AlertWebhookUrl = "",
    [string]$TwilioFromNumber = "",
    [string]$TwilioAccountSid = "",
    [string]$TwilioAuthToken = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Setting user-level alert environment variables..."
[Environment]::SetEnvironmentVariable("ALERT_TO_NUMBER", $AlertToNumber, "User")

if ($NtfyTopic) {
    [Environment]::SetEnvironmentVariable("NTFY_TOPIC", $NtfyTopic, "User")
}
if ($NtfyUrl) {
    [Environment]::SetEnvironmentVariable("NTFY_URL", $NtfyUrl, "User")
}
if ($TelegramBotToken) {
    [Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", $TelegramBotToken, "User")
}
if ($TelegramChatId) {
    [Environment]::SetEnvironmentVariable("TELEGRAM_CHAT_ID", $TelegramChatId, "User")
}
if ($AlertWebhookUrl) {
    [Environment]::SetEnvironmentVariable("ALERT_WEBHOOK_URL", $AlertWebhookUrl, "User")
}
if ($TwilioFromNumber) {
    [Environment]::SetEnvironmentVariable("TWILIO_FROM_NUMBER", $TwilioFromNumber, "User")
}
if ($TwilioAccountSid) {
    [Environment]::SetEnvironmentVariable("TWILIO_ACCOUNT_SID", $TwilioAccountSid, "User")
}
if ($TwilioAuthToken) {
    [Environment]::SetEnvironmentVariable("TWILIO_AUTH_TOKEN", $TwilioAuthToken, "User")
}

Write-Host "Done."
Write-Host "ALERT_TO_NUMBER set to $AlertToNumber"
Write-Host ""
Write-Host "Free recommendation: set NTFY_TOPIC (or NTFY_URL) for push alerts."
Write-Host "Optional free alternative: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID."
Write-Host ""
Write-Host "Legacy paid fallback (Twilio SMS):"
Write-Host " - TWILIO_ACCOUNT_SID"
Write-Host " - TWILIO_AUTH_TOKEN"
Write-Host " - TWILIO_FROM_NUMBER"
Write-Host ""
Write-Host "Generic webhook is also supported via ALERT_WEBHOOK_URL."

