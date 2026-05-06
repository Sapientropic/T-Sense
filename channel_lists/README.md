# Channel Lists

This directory holds text files listing Telegram channels to scan.

## Format

One channel name per line. Lines starting with `#` are comments. Empty lines are ignored.

```
# My job search channels
remote_italic
dev_jobs_remote
react_jobs
```

## Usage

```bash
# Scan with a specific list
scripts/scan.sh channel_lists/my-jobs.txt 24

# Or use a precise cutoff
scripts/scan.sh channel_lists/my-jobs.txt --since 2026-05-06T07:30:00Z

# On Windows
scripts\scan.bat channel_lists\my-jobs.txt 24
```

## Tips

- Keep lists under 50 channels per scan for smooth operation (no hard limit — just rate limiting)
- Group channels by topic into separate files (e.g., `frontend.txt`, `devops.txt`)
- The number after the list file is the time window in hours (default: 24)
- If a high-volume channel reaches the scanner cap, raise `SCAN_MAX_LIMIT` or narrow the window. The scanner reports incomplete results instead of silently dropping messages.
