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

# On Windows
scripts\scan.bat channel_lists\my-jobs.txt 24
```

## Tips

- Keep lists under 25 channels to stay within safe usage limits
- Group channels by topic into separate files (e.g., `frontend.txt`, `devops.txt`)
- The number after the list file is the time window in hours (default: 24)
