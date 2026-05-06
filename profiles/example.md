# Candidate Profile: Frontend Developer

## Basic Info
- **Role**: Frontend Developer (Middle/Senior)
- **Experience**: 5 years
- **Preferred format**: Remote
- **Location constraint**: Russia office NOT acceptable
- **Timezone**: Flexible (remote-first)

## Tech Stack
- **Core**: React, TypeScript, Next.js
- **State management**: Redux Toolkit, RTK Query
- **UI libraries**: Material UI (MUI), Ant Design, Tailwind CSS
- **Tools**: Git, Figma, REST APIs

## Preferences
- Priority: Remote-first companies or fully distributed teams
- Interested in: product companies, fintech, edtech, SaaS
- Not interested in: outsourcing agencies, government projects
- Salary expectation: Competitive market rate for Senior Frontend

## Search Rules
1. Only include jobs posted within the last 24 hours
2. Remove duplicates (same company + same title)
3. Rate each match: **high** / **medium** / **low**
4. For high matches, include direct application link if available
5. Output in structured Markdown with sections: High Match → Medium Match → Low Match

## Report Preferences
- Keep low-priority roles when they are useful boundary examples, such as Russia office-only or junior roles
- Preserve contact details when they are needed for applying
- Explain why each high match is worth applying to now
- For medium matches, state exactly what needs to be verified before applying
- For low matches, state which criterion would need to change

---

*Copy this file and customize for your own profile:*
```bash
cp profiles/example.md profiles/my-profile.md
# Edit profiles/my-profile.md with your details
```

---

*Advanced: to customize extraction schema, prompts, or report labels, add the
optional sections below to your profile. If omitted, the built-in job-mode
defaults are used.*

<!--
## Extraction Schema
mode: job
top_level_key: jobs
dedup_fields: [company, role]
fields:
  - name: company
    required: true
  - name: role
    required: true
  - name: location
  - name: salary
  - name: contact
    extract_all: true
  - name: link
  - name: source
  - name: rating
    values: [high, medium, low]
  - name: why
  - name: stack
    type: list
  - name: concerns
    type: list
  - name: action
    values: [Apply, Inspect, "Skip unless criteria change"]

## Extraction Prompt
system_prompt: |
  You extract job listings from Telegram messages...

## Report Labels
report_title: "Job Scan Report"
section_high: "Highly Recommended (apply now)"
section_medium: "Worth Investigating (check details first)"
section_low: "Low Priority (only if criteria change)"
stats_label: "Matches"
output_filename: "job-scan-report-{date}.md"
-->
