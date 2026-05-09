# Profile: Developer Opportunity Leads

## Basic Info
- **Role**: Frontend / full-stack developer opportunities worth acting on
- **Level**: Middle to senior, or specialist contract work with clear budget
- **Work format**: Remote, clearly relocation-friendly, contract, freelance, or Mini Apps / TON project work
- **Location exclusions**: On-site only roles in rejected locations

## Search Rules
1. Include roles, contract projects, freelance gigs, and Mini Apps / TON work that match the target stack, seniority, and work format.
2. Rate each item as high, medium, or low.
3. Keep low-priority items only when they explain a useful boundary.
4. Preserve contact handles, emails, application links, budget, and payment clues.
5. For fast alerts, rate high only when the role is worth acting on within the next hour.
6. Treat keyword prefilter hits as candidates only; the final rating must still be based on fit, freshness, and actionability.

## Prefilter Tuning
- Suggest adding keywords when missed good roles share a repeated phrase.
- Suggest removing keywords when they repeatedly create false positives.
- Prefer phrases that imply an actual opening, not generic stack terms alone.

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [company, role]
fields:
  - name: source_message_refs
    type: list
  - name: source_message_ids
    type: list
  - name: opportunity_type
    values: [job, contract, freelance_gig, mini_app_ton_project, other]
  - name: company
  - name: role
    required: true
  - name: location
  - name: salary
  - name: budget
  - name: contact
  - name: apply_url
  - name: deadline
  - name: posted_at_hint
  - name: urgency_reason
  - name: rating
    values: [high, medium, low]
  - name: why
  - name: action
    values: [Apply, Inspect, Skip unless criteria change]

## Extraction Prompt
system_prompt: |
  Extract only real developer opportunities: job openings, contract roles,
  freelance gigs, paid Mini Apps / TON projects, or clearly actionable hiring
  leads. Prefer a compact item over a verbose explanation. Return at most 8 items,
  ranked by near-term actionability and profile fit. If a digest contains
  many opportunities, extract only the top 3 matching items from that digest.
  Return no item for generic career discussion, job-board navigation, course
  ads, repeated channel promo text, low-confidence guesses, unpaid vague ideas,
  or roles that are clearly off-profile. Do not copy full job descriptions; keep
  why, action, and urgency_reason to one short sentence each.

## Report Preferences
- Explain why high-priority leads deserve action today.
- Put urgent high-priority opportunities first and explain the fastest safe next step.
- For medium matches, state what must be verified before applying.
- For low matches, state which criterion would need to change.

## Report Labels
report_title: "Developer Opportunity Signal Report"
section_high: "Apply Today"
section_medium: "Inspect First"
section_low: "Boundary Examples"
stats_label: "Developer opportunities"
output_filename: "job-signal-report-{date}.md"
profile_section_title: "Developer Opportunity Profile"
methodology_label: "Telegram opportunity channels"
