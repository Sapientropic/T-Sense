# TG Channel Scanner

Read Telegram channel messages on demand, filter by keywords/profiles, and generate AI-powered digests.

Designed for job seekers monitoring multiple Telegram job channels, but works for any channel monitoring use case.

[**中文文档**](README.zh-CN.md)

---

## Quick Start

### Prerequisites

- Python 3.12+
- Telegram account (phone number)
- Telegram API credentials (`api_id` + `api_hash` from [my.telegram.org/apps](https://my.telegram.org/apps))

### Install

```bash
git clone https://github.com/Sapientropic/tg-channel-scanner.git
cd tg-channel-scanner
chmod +x setup.sh scripts/scan.sh
./setup.sh
```

> `setup.sh` installs pinned dependencies from `requirements.txt` / `requirements-llm.txt`, verifies [pytgcli](https://github.com/tksohishi/tgcli) provides the expected `tg` command, and writes config to `~/.config/tgcli/config.toml`.

### Configure

```bash
# 1. Edit config with your Telegram API credentials
#    (setup.sh created it at ~/.config/tgcli/config.toml)
nano ~/.config/tgcli/config.toml

# 2. Activate venv and login to Telegram
source .venv/bin/activate
tg auth login

# 3. Verify
tg auth status
```

### Run a scan

```bash
# Scan all channels in a list, past 24 hours
./scripts/scan.sh channel_lists/example.txt

# Scan past 7 days
./scripts/scan.sh channel_lists/example.txt 168

# Scan since a precise ISO-8601 cutoff
./scripts/scan.sh channel_lists/example.txt --since 2026-05-06T07:30:00Z

# Output goes to output/scan_YYYYMMDD_HHMMSS.jsonl
# Errors go to output/scan_YYYYMMDD_HHMMSS.errors.log
```

The scanner uses an exact UTC cutoff. Because `tgcli` currently accepts date-only `--after` values, the wrapper over-reads from that UTC date and filters JSONL locally. It increases `tg read --limit` until the result is no longer saturated; if a channel still reaches `SCAN_MAX_LIMIT`, the scan exits non-zero and marks that channel incomplete instead of silently dropping messages.

Useful environment variables:

```bash
SCAN_INITIAL_LIMIT=200   # first tg read limit per channel
SCAN_MAX_LIMIT=5000      # hard cap before reporting incomplete
SCAN_DELAY=1             # seconds between channels
```

### Summarize with AI

```bash
# Option 1: Python script (OpenAI-compatible API)
export OPENAI_API_KEY=sk-your-key
python scripts/summarize.py --input output/scan_XXXX.jsonl --profile profiles/example.md

# Optional: redact emails, phone numbers, and Telegram handles before sending
python scripts/summarize.py --input output/scan_XXXX.jsonl --profile profiles/example.md \
  --redact-contact-info

# Works with DeepSeek, Ollama, etc:
python scripts/summarize.py --input output/scan_XXXX.jsonl --profile profiles/example.md \
  --base-url https://api.deepseek.com/v1 --model deepseek-chat

# Option 2: Feed output directly to Codex / Claude / any AI agent
#   Point your agent at:
#   - The JSONL scan file in output/
#   - Your profile in profiles/
#   Example Codex prompt:
#     "Read output/scan_XXXX.jsonl and filter jobs matching profiles/my-profile.md"
```

`summarize.py` sends the selected JSONL messages and profile to your configured OpenAI-compatible API. Telegram messages are treated as untrusted content in the prompt, but you should still review your LLM provider's privacy/data-use terms before sending private channel data.

---

## How It Works

```
Telegram Channels
  → tgcli reads messages (JSONL, date floor)
    → scanner filters exact cutoff + completeness
    → saved to output/
      → AI agent filters + summarizes
        → structured report
```

1. **Read**: `tgcli` (Telethon-based CLI) reads messages from channels you've subscribed to
2. **Filter**: `scripts/scan.py` filters by precise timestamp and refuses to silently accept saturated limits
3. **Save**: Messages are saved as JSONL with date, sender, text, channel info
4. **Summarize**: Your preferred LLM generates a filtered, deduplicated report

## Directory Structure

```
tg-channel-scanner/
├── config.example.toml      # Template (actual config at ~/.config/tgcli/)
├── requirements.txt         # Pinned scanner dependency
├── requirements-llm.txt     # Pinned optional summarizer dependency
├── setup.sh                 # One-command installer
├── profiles/                # Candidate/filter profiles
│   └── example.md           # Example: Frontend Developer job search
├── channel_lists/           # Channel name lists (one per line)
│   └── example.txt          # Example channel list
├── scripts/
│   ├── scan.sh              # Batch channel reader (Mac/Linux)
│   ├── scan.bat             # Batch channel reader (Windows)
│   ├── scan.py              # Cross-platform scanner core
│   └── summarize.py         # Optional LLM summarizer
├── output/                  # Scan results (gitignored)
└── docs/
    ├── tos-risk-analysis.md
    └── getting-api-credentials.md
```

## Creating Your Own Profile

Copy `profiles/example.md` and edit the matching criteria. The profile tells the AI what to filter for:

```markdown
## Candidate
- Role: Frontend Developer
- Stack: React, TypeScript, Next.js
- Level: Middle/Senior
- Location: Remote preferred

## Filter Rules
- Only include jobs from last 24 hours
- Remove duplicates (same company + title)
- Exclude: Backend-only, Mobile, DevOps...
```

## Creating Your Own Channel List

Create a `.txt` file in `channel_lists/`. Use **Telegram channel usernames** (not display names), one per line:

```
# Good — these are Telegram usernames
remote_italic
dev_jobs_remote
react_jobs

# BAD — these are display names, won't work
React Job | JavaScript | Вакансии
```

> How to find a channel's username: open the channel in Telegram → tap the name → look for @username.

Lines starting with `#` are comments.

## Safety & Telegram ToS

This tool reads messages from channels you've already subscribed to — equivalent to scrolling through them manually.

**Key points:**
- No hard limit on channels — 50+ is fine with 1-second delays between reads
- On-demand scans: no limit
- Automated scans: daily is safe, more frequent is fine too
- Use your real account (not a new/virtual number account)

The main constraint is Telegram's **FloodWaitError** (rate limiting), not account bans. See [docs/tos-risk-analysis.md](docs/tos-risk-analysis.md) for full details.

## Windows

```bat
setup.bat
```

This creates config at `%USERPROFILE%\.config\tgcli\config.toml` — edit it with your API credentials, then:

```bat
call .venv\Scripts\activate.bat
tg auth login
scripts\scan.bat channel_lists\example.txt
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `tg: command not found` | Activate venv first: `source .venv/bin/activate` |
| `Permission denied` on `.sh` | `chmod +x setup.sh scripts/scan.sh` |
| my.telegram.org shows ERROR | See [docs/getting-api-credentials.md](docs/getting-api-credentials.md) |
| 0 messages collected | Check `output/*.errors.log` for failures |
| Scan exits with incomplete channel | Raise `SCAN_MAX_LIMIT` or narrow the time window; the script refused to claim completeness after reaching the cap |
| tgcli version mismatch during setup | Re-run setup after checking `requirements.txt`; this repo is verified against pinned `pytgcli` |

## License

MIT
