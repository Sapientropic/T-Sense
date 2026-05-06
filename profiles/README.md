# Profiles

This directory holds Markdown files describing your filtering criteria for AI-powered report generation.

## Modes

**Job mode** (default): no special sections needed. The built-in extraction schema, prompts, and report labels are used automatically. See `example.md`.

**Custom mode**: add optional sections to your profile to override the defaults. The extraction schema, system prompt, and report labels are all configurable. See `example-airdrop.md` for a complete custom-mode example.

| Optional section | What it controls |
|-----------------|-----------------|
| `## Extraction Schema` | Field definitions, dedup keys, mode name |
| `## Extraction Prompt` | System prompt, location/contact filter overrides |
| `## Report Labels` | Report title, section headers, output filename |

If no optional sections are present, job-mode defaults are used — backward compatible.

## Format

A profile tells the AI what to filter for. Basic sections:

```markdown
# Profile: Frontend Developer

## Basic Info
- **Role**: Frontend Developer (Middle/Senior)
- **Experience**: 5 years
- **Preferred format**: Remote

## Tech Stack
- **Core**: React, TypeScript, Next.js
- **UI libraries**: Material UI, Tailwind CSS

## Search Rules
1. Only include items posted within the last 24 hours
2. Remove duplicates
3. Rate each match: **high** / **medium** / **low**
```

## Usage

```bash
# Generate report with a specific profile
python scripts/report.py --input output/scan_XXXX.jsonl --profile profiles/my-profile.md --output output/report.md

# Pipeline: scan + report in one command
python scripts/daily_report.py channel_lists/my-channels.txt --profile profiles/my-profile.md --html

# Redact emails, phone numbers, and Telegram handles before sending to the LLM
python scripts/report.py --input output/scan_XXXX.jsonl --profile profiles/my-profile.md --redact-contact-info
```

## Tips

- Keep profiles focused — a generic profile produces generic results
- Create multiple profiles for different use cases (e.g., `frontend-jobs.md`, `airdrops.md`, `news.md`)
- Update profiles as your preferences change
- Do not put secrets, API keys, private notes, or unrelated personal data in profiles. The report generator sends the profile to your configured LLM API.
