# Telegram ToS Risk Analysis

## TL;DR

Reading your own Telegram messages at a reasonable frequency is safe. Bulk scraping, data collection for AI training, or aggressive polling is not.

## What's Allowed

- Reading messages from channels you've joined via your own account
- Automated summaries for personal use (job hunting, news digests)
- Scanning at reasonable intervals (≤ once per day)
- Reading a reasonable number of channels (≤ 25)

## What's NOT Allowed

- **Bulk data collection** for AI training, resale, or redistribution
- **Aggressive polling** (multiple times per hour)
- **Scraping public channels you haven't joined** at scale
- **Selling or redistributing** scraped message data
- **Impersonation** or unauthorized access to other users' accounts

## Our Usage Pattern

This tool is designed for **personal job search assistance**:

| Parameter | Recommended Limit |
|-----------|-------------------|
| Scan frequency | ≤ 1× per day |
| Channels per scan | ≤ 25 |
| Messages per channel | ≤ 100 |
| Delay between channels | ≥ 1 second |
| Data retention | Delete after summarization |

## Why These Limits

Telegram's abuse detection looks for:
1. **High-frequency API calls** — rapid-fire reads trigger rate limits
2. **Large-scale data export** — reading thousands of messages across hundreds of channels
3. **Account behavior anomalies** — automated patterns that don't match normal use

Our scan.sh includes a 1-second sleep between channels and limits reads to 100 messages per channel specifically to stay within normal usage patterns.

## What Happens If You Exceed Limits

- First: Temporary rate limiting (a few hours)
- Repeated: Account restricted (24h - 7 days)
- Severe/abusive: Account ban

## Mitigation

- Run scans manually, not on a cron schedule
- Keep channel lists focused (don't add channels you don't actually read)
- Don't share your API credentials
- Don't store raw message data long-term

## Legal Disclaimer

This analysis is based on Telegram's Terms of Service as of 2026-05. Telegram may update their policies at any time. Use this tool responsibly and at your own risk.
