# Monitor: Crypto Airdrops

## Basic Info
- **Focus**: New token airdrops, testnet campaigns, bounty programs
- **Chains**: Ethereum, Solana, Base, Arbitrum
- **Priority**: Early-stage projects with confirmed tokens
- **Not interested in**: Pure speculation, referral-farming only

## Preferences
- Prefer campaigns with clear token distribution timeline
- Track testnet participation opportunities
- Flag high-effort campaigns requiring daily tasks

## Search Rules
1. Only include campaigns posted within the scan window
2. Remove duplicates (same project)
3. Rate each match: **high** / **medium** / **low**
4. Include direct links to project websites or claim pages

## Report Preferences
- Show deadline or "No deadline" for each campaign
- Highlight chains the campaign is on
- Flag if KYC is required

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [project]
fields:
  - name: project
    required: true
  - name: type
    values: [airdrop, testnet, bounty, grant, campaign]
  - name: chain
    type: list
  - name: reward
  - name: deadline
  - name: link
  - name: requirements
    type: list
  - name: kyc_required
  - name: rating
    values: [high, medium, low]
  - name: why
  - name: concerns
    type: list
  - name: action
    values: [Participate, Research, Skip]

## Extraction Prompt
system_prompt: |
  You extract crypto airdrop, testnet, bounty, and campaign opportunities from Telegram messages.
  Focus on actionable opportunities that users can participate in.
  Exclude pure spam, referral-only links, and vague announcements without concrete details.

## Report Labels
report_title: "Airdrop Monitor"
section_high: "Act Now (limited time)"
section_medium: "Research First"
section_low: "Low Priority"
stats_label: "Airdrop matches"
output_filename: "airdrop-report-{date}.md"
profile_section_title: "Monitor Profile"
methodology_label: "Telegram crypto channels"
