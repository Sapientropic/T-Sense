# Profiles

This directory holds Markdown files describing your candidate profile or filtering criteria for AI summarization.

## Format

A profile tells the AI what to filter for. Include your role, tech stack, preferences, and rules:

```markdown
# Candidate Profile: Frontend Developer

## Basic Info
- **Role**: Frontend Developer (Middle/Senior)
- **Experience**: 5 years
- **Preferred format**: Remote

## Tech Stack
- **Core**: React, TypeScript, Next.js
- **UI libraries**: Material UI, Tailwind CSS

## Search Rules
1. Only include jobs posted within the last 24 hours
2. Remove duplicates (same company + same title)
3. Rate each match: **high** / **medium** / **low**
```

## Usage

```bash
# Summarize with a specific profile
python scripts/summarize.py --input output/scan_YYYYMMDD_HHMMSS.jsonl --profile profiles/my-profile.md
```

## Tips

- Keep profiles focused — a generic profile produces generic results
- Create multiple profiles for different job searches (e.g., `frontend.md`, `fullstack.md`)
- Update profiles as your preferences or skills change
