# Backfill 2023-2024 + top-ups (owner-authorized pre-cancellation archive pull)
# Sequential, resumable (per-event raw cache), closes-first per snapshot tier.
# Log: data/Odds-Historical/theoddsapi/pull_2023_2024.log
$ErrorActionPreference = "Continue"
$puller = "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\production\ops\market_research\pull_oddsapi_historical.py"
$MK15 = "pitcher_strikeouts,pitcher_strikeouts_alternate,pitcher_outs,pitcher_walks,pitcher_hits_allowed,pitcher_earned_runs,batter_strikeouts,batter_home_runs,batter_hits,batter_total_bases,batter_rbis,batter_walks,batter_hits_runs_rbis,batter_runs_scored,batter_singles"

function Run-Pull($label, $args) {
    Write-Output "=== $label $(Get-Date -Format o)"
    python $puller @args
    Write-Output "=== $label exit=$LASTEXITCODE $(Get-Date -Format o)"
}

# Tier 1a: 2023 season (+postseason) close then morning (no open18: 404-verified dead in 2023)
Run-Pull "2023-close"   @("pull", "--start", "2023-05-03", "--end", "2023-10-31", "--markets", $MK15, "--snapshots", "close",   "--max-credits", "650000")
Run-Pull "2023-morning" @("pull", "--start", "2023-05-03", "--end", "2023-10-31", "--markets", $MK15, "--snapshots", "morning", "--max-credits", "650000")
# Tier 1b: 2024 season (+postseason) close, morning, open18 (open18 verified live in 2024)
Run-Pull "2024-close"   @("pull", "--start", "2024-03-15", "--end", "2024-10-31", "--markets", $MK15, "--snapshots", "close",   "--max-credits", "650000")
Run-Pull "2024-morning" @("pull", "--start", "2024-03-15", "--end", "2024-10-31", "--markets", $MK15, "--snapshots", "morning", "--max-credits", "650000")
Run-Pull "2024-open18"  @("pull", "--start", "2024-03-15", "--end", "2024-10-31", "--markets", $MK15, "--snapshots", "open18",  "--max-credits", "650000")
# Tier 2: 2025 batter_strikeouts top-up (only market missing from 2025 close/morning)
Run-Pull "2025-bk-topup" @("pull", "--start", "2025-03-01", "--end", "2025-10-31", "--markets", "batter_strikeouts", "--snapshots", "close,morning", "--max-credits", "80000")
# Tier 3: 2025-2026 open18 for all 15 markets (earliest usable pregame clock)
Run-Pull "2025-open18" @("pull", "--start", "2025-03-01", "--end", "2025-10-31", "--markets", $MK15, "--snapshots", "open18", "--max-credits", "800000")
Run-Pull "2026-open18" @("pull", "--start", "2026-03-01", "--end", "2026-09-28", "--markets", $MK15, "--snapshots", "open18", "--max-credits", "800000")
# Final: rebuild normalized book-lines from ALL raw snapshots
Run-Pull "normalize" @("normalize")
Write-Output "=== ALL DONE $(Get-Date -Format o)"
