state: doc_debt_cleaned_graphify_refresh_synced
mode: Standard
slice_goal: "Keep the technical-debt authority current, keep handoff compact, and keep the local Graphify advisory snapshot fully synced after material corpus changes."
authority_note: "Current technical-debt status lives in docs/technical-debt-cleanup-spec.md; command recipes live in docs/testing.md; recurring Graphify/doc-debt sweep records live in local ignored docs/graphify-maintenance/; local graph artifacts remain advisory only."
gate_status: passed
blockers: []

current_truth:
  - "Branch now: master; worktree clean; origin/master...HEAD = 0 0."
  - "GitHub issue #7 remains historical evidence, not current open debt."
  - "Technical-debt authority remains docs/technical-debt-cleanup-spec.md; command authority remains docs/testing.md."
  - "2026-05-16 corpus detection succeeded: 340 files, 302 code files, 38 doc files, about 244331 words."
  - "2026-05-16 AST refresh succeeded locally: 302 expanded code files, 3918 AST nodes, 8905 AST edges."
  - "2026-05-16 MiniMax semantic refresh succeeded: 38 semantic files, 31 cached files, 7 uncached files, 76 semantic nodes, 160 semantic edges, 10230 input tokens, 5985 output tokens."
  - "2026-05-16 public Graphify snapshot is now synced again: 3981 nodes, 7410 edges, 33 communities, density 0.000935347422871706, directory_fallback clustering, graph.html written."
  - "Hotspot recheck: dashboard_server.py 954, review-card.tsx 867, profile_patches.py 970, report_extraction.py 767, desk_scheduler.py 906, desk_actions.py 701, sanitize/desk.ts 784, domain/types.ts 684, dashboard_projection.py 544."

graphify_status:
  - "The previous write failure was environmental, not a repo ACL problem: this session can overwrite graphify-out public artifacts directly."
  - "The public advisory snapshot is now current for the 2026-05-16 corpus. Read graphify-out/README.md first, then GRAPH_REPORT.md, then graph.json."
  - "Keep treating EXTRACTED anchors as routing evidence that still needs repo-file verification."

verification:
  - "python ensure_graphify.py -> graphifyy 0.8.4 on Python 3.11."
  - "detect_corpus.py -> 340 files, 38 docs, 302 code, graph rebuild warranted."
  - "extract_ast.py succeeded directly on the Graphify Python 3.11 runtime: 302 expanded code files, 3918 AST nodes, 8905 AST edges."
  - "extract_minimax_semantic.py succeeded directly, selected MINIMAX_TOKEN_PLAN_KEY first, and refreshed the 7 uncached docs."
  - "assemble_graph.py succeeded and rewrote GRAPH_REPORT.md, graph.json, graph.html, manifest.json, and cost.json."
  - "Focused stale-claim greps confirmed the old one-commit-ahead branch claim and stale needs_update wording are gone."

next_action: "Use docs/technical-debt-cleanup-spec.md for the next cleanup slice. If a future run reports write failures again, treat that as session-environment drift first and verify direct overwrite of GRAPH_REPORT.md before changing repo files or ACLs."
