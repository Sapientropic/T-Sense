state: documentation_authority_graphify_sync
mode: Standard
run_shape: local_doc_debt_sweep
slice_goal: "Keep the active handoff aligned with the real repository state, current authority boundaries, and the latest local Graphify evidence."
authority_note: "This file is only the compact active handoff. Product direction lives in ROADMAP.md; route/agent contracts live in docs/agent-cli-contract.md; platform notes live in docs/desktop-platforms.md; debt guardrails live in docs/technical-debt-cleanup-spec.md; dated quality logs remain historical evidence."
gate_status: passed
blockers:
  - "Local master remains behind origin/master by 1 commit on the current remote-tracking refs; pull or reconcile upstream before the next product-change slice."

current_truth:
  - "Branch: master; current local remote-tracking refs show origin/master ahead by 1 commit (`cd77f6e fix: restart dashboard after app updates`), and the tracked local diff now consists of this documentation/Graphify sweep."
  - "The 2026-05-17 Mini App/source-learning contract refresh is already committed locally as `1a57f94`; the old 'split commits then push master' handoff is no longer current."
  - "Technical-debt status authority remains docs/technical-debt-cleanup-spec.md, command authority remains docs/testing.md, and local Graphify artifacts remain advisory evidence only."
  - "docs/graphify-maintenance/ stays local/ignored and excluded from the graph corpus via .graphifyignore, so recurring sweep notes remain reviewable without becoming graph noise."
  - "The 2026-05-18 Graphify rebuild detected a materially larger corpus (357 files / about 279731 words), refreshed AST extraction through a sequential fallback, reran MiniMax semantic extraction successfully against 14 uncached docs, and published a synced local advisory snapshot."
  - "The refreshed local graph snapshot now reports 4359 nodes, 8291 edges, 32 communities, 79 semantic nodes, 195 semantic edges, and 30274 input / 10676 output semantic tokens."
  - "The earlier root-level Graphify temp-file debris was cleaned successfully in the current write-capable session, so the previous temp-file blocker is resolved."
  - "Mini App/source-learning product behavior still follows the committed docs: local preview is safe, Telegram install requires a user-approved public HTTPS /miniapp URL, and source intake remains metadata-only."

active_scope:
  - "Compact documentation-debt cleanup only: stale current-state claims, duplicated graph snapshot status, obsolete handoff guidance, and graph corpus boundary checks."
  - "Authority alignment across docs/technical-debt-cleanup-spec.md, docs/testing.md, docs/quality/task-state.md, .graphifyignore, and graphify-out/README.md."
  - "Local Graphify refresh and maintenance logging after documentation-boundary changes."

verification:
  - "This sweep verifies documentation truth with git status/log, focused stale-claim greps, git diff --check, detect_corpus.py, a sequential no-cache AST fallback, a successful MiniMax semantic-helper run against graphify-out, assemble_graph.py publishing to graphify-out, and temp-file cleanup verification."

next_action: "Review the current documentation/Graphify diff, then pull or reconcile the one upstream master commit before the next product slice."
