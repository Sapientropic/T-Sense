export type SourceRef = {
  channel: string;
  id: string | number;
  url?: string;
};

export type DecisionState = {
  status?: string;
  signals?: string[];
  explanations?: Record<string, string>;
  seen_count?: number;
  first_seen_at?: string;
  last_seen_at?: string;
  material_change_fields?: string[];
};

export type ReviewCard = {
  schema_version: "review_card_v1";
  card_id: string;
  profile_id: string;
  title: string;
  rating: string;
  decision_status: string;
  source_refs: SourceRef[];
  item: {
    why?: string;
    decision_state?: DecisionState;
  };
  status: string;
  opportunity_status: "open" | "saved" | "applied" | "contacted" | "dismissed" | "duplicate" | string;
  opportunity_updated_at: string;
  duplicate_of_card_id?: string | null;
  first_run_id?: string;
  last_run_id?: string;
  alert_summary?: ReviewCardAlertSummary;
  report_path?: string;
  dashboard_url?: string;
  updated_at: string;
};

export type ReviewCardAlertSummary = {
  schema_version?: "review_card_alert_summary_v1";
  alert_count: number;
  latest_status?: string;
  latest_run_id?: string;
  latest_target_id?: string;
  latest_target_type?: string;
  latest_delivery_mode?: string;
  latest_delivery_status?: string;
  latest_delivery_ok?: boolean;
  latest_alerted_at?: string;
};

export type Profile = {
  profile_id: string;
  display_name?: string;
  report_display_name?: string;
  display_path?: string;
  enabled: boolean;
  alert_schedule_mode?: string;
  source_topics?: string[];
  scan_window_hours?: number;
  semantic_max_messages?: number;
  timezone?: string;
  workdays?: string[];
  work_start?: string;
  work_end?: string;
  work_interval_minutes?: number;
  off_hours_interval_minutes?: number;
  alert_rule?: string;
  alert_max_age_minutes?: number;
  delivery_target_count?: number;
  matching_profile?: ProfileMatchingProfile;
  updated_at: string;
};

export type ProfileRuntimeSettings = {
  scan_window_hours?: number;
  semantic_max_messages?: number;
  timezone?: string;
  workdays?: string[];
  work_start?: string;
  work_end?: string;
  work_interval_minutes?: number;
  off_hours_interval_minutes?: number;
  alert_rule?: string;
  alert_max_age_minutes?: number;
};

export type ProfileMatchingProfile = {
  schema_version?: "profile_matching_profile_v1";
  summary?: string;
  sections: ProfileMatchingSection[];
  learned_preferences: string[];
  editable_text?: string;
};

export type ProfileMatchingSection = {
  key: string;
  label: string;
  items: string[];
};

export type SourceStat = {
  channel: string;
  display_name?: string;
  card_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  pending_count: number;
  handled_count: number;
  false_positive_count: number;
  alert_count: number;
  high_rate: number;
  latest_card_count?: number;
  latest_high_count?: number;
  raw_count?: number;
  kept_count?: number;
  scan_keep_rate?: number;
  card_yield_rate?: number;
  latest_run_id?: string;
  scan_failure?: boolean;
  scan_failure_reason?: string;
  scan_incomplete?: boolean;
};

export type SourceInsight = {
  kind: "promote" | "prune" | "watch" | string;
  channel: string;
  display_name?: string;
  label: string;
  reason: string;
  priority: number;
  confidence?: string;
  next_action?: {
    label?: string;
    detail?: string;
    command?: string;
  };
  stats: SourceStat;
};

export type SourceImportResult = {
  schema_version?: "desk_source_import_result_v1";
  dry_run: boolean;
  written: boolean;
  topic: string;
  added_count: number;
  updated_count: number;
  unchanged_count: number;
  removed_count?: number;
  enabled_count?: number;
  disabled_count?: number;
  source_count: number;
  registry_path: string;
  preview_sources: Array<{
    label: string;
    source_id: string;
  }>;
  resolved_plan?: {
    add: string[];
    remove: string[];
    disable: string[];
    enable: string[];
  };
  preview_truncated_count: number;
  action?: string;
  llm_used?: boolean;
  title?: string;
  detail?: string;
  next_action?: string;
  finished_at?: string;
};

export type DeskSource = {
  schema_version?: "desk_source_v1";
  source_id: string;
  label: string;
  channel: string;
  enabled: boolean;
  topics: string[];
  priority: string;
  scan_window_hours: number;
};

export type DeskSourcesResult = {
  schema_version?: "desk_sources_v1";
  source_count: number;
  enabled_count: number;
  topics: string[];
  registry_path: string;
  sources: DeskSource[];
};

export type DeskNotificationTokenStatus = {
  schema_version: "desk_notification_token_status_v1";
  configured: boolean;
  verification_status?: string;
  source: string;
  updated_at?: string | null;
  env_configured: boolean;
  local_store_supported: boolean;
  local_store_configured: boolean;
  local_store_backend?: string;
  local_store_label?: string;
  can_save: boolean;
  can_clear: boolean;
  platform: string;
  detail: string;
};

export type DeskBotGatewayStatus = {
  schema_version: "desk_bot_gateway_status_v1";
  token_configured: boolean;
  authorized_chat_count: number;
  gateway_status: "running" | "stale" | "not_detected" | string;
  commands_installed: boolean;
  supported_commands: string[];
  local_first_note: string;
  start_command: string;
  last_update_at?: string;
  last_error?: string;
  safe_next_action?: string;
  background: DeskBotGatewayBackgroundStatus;
  started_at?: string;
  last_poll_at?: string;
};

export type DeskBotGatewayBackgroundStatus = {
  schema_version: "desk_bot_gateway_background_status_v1";
  backend: string;
  available: boolean;
  installed: boolean;
  status: "installed" | "not_installed" | "manual" | "unavailable" | "unknown" | string;
  can_install: boolean;
  can_remove: boolean;
  detail: string;
  next_action: string;
  checked_at?: string;
};

export type DeskBotIdentityResult = {
  schema_version: "bot_identity_apply_result_v1";
  name: string;
  description_updated: boolean;
  short_description_updated: boolean;
  commands_installed: boolean;
  profile_photo_updated: boolean;
};

export type DeskAiProviderStatus = {
  provider: string;
  label: string;
  env_name: string;
  purpose?: string;
  configured: boolean;
  verification_status?: string;
  usable_for_matching?: boolean;
  source: string;
  env_configured: boolean;
  local_store_configured: boolean;
  local_store_backend?: string;
  local_store_label?: string;
  can_save: boolean;
  can_clear: boolean;
  updated_at?: string | null;
  detail: string;
};

export type DeskAiSettingsStatus = {
  schema_version: "desk_ai_settings_status_v1";
  configured_count: number;
  matching_configured_count?: number;
  ocr_configured_count?: number;
  local_store_supported: boolean;
  local_store_backend?: string;
  local_store_label?: string;
  platform: string;
  detail: string;
  providers: DeskAiProviderStatus[];
  checked_at?: string;
};

export type DashboardNextAction = {
  label?: string;
  detail?: string;
  command?: string;
  target?: string;
  target_tab?: string;
  action_id?: string;
  artifact_path?: string;
};

export type FeedbackImpact = {
  card_id?: string;
  created_at?: string;
  profile_id?: string;
  action?: string;
  item_title?: string;
  rating?: string;
  decision_status?: string;
  impact_type?: string;
  impact_status?: string;
  impact_label?: string;
  impact_detail?: string;
  patch_id?: string;
};

export type FeedbackCalibrationSummary = {
  schema_version?: "feedback_calibration_summary_v1";
  latest_applied_at?: string;
  runs_after_latest_apply?: number;
  cards_after_latest_apply?: number;
  high_cards_after_latest_apply?: number;
  feedback_after_latest_apply?: number;
  false_positive_after_latest_apply?: number;
  high_rate_after_latest_apply?: number;
  next_action?: DashboardNextAction;
};

export type RunArtifact = {
  type?: string;
  path: string;
  sha256?: string;
  category?: string;
  format?: string;
  display_name?: string;
  display_path?: string;
};

export type Run = {
  run_id: string;
  profile_id: string;
  display_name?: string;
  status: string;
  started_at: string;
  completed_at?: string;
  alert_count?: number;
  review_card_count?: number;
  report_artifact?: RunArtifact | null;
  quality?: {
    prefilter?: string;
    semantic_stage?: string;
    llm_provider?: string;
    cache_hit_rate?: number | null;
    latency_ms?: number | null;
    completion_tokens?: number | null;
    diagnostic_count?: number;
    diagnostic_failure_count?: number;
    diagnostic_warning_count?: number;
    diagnostic_info_count?: number;
    top_diagnostic_code?: string;
  };
};

export type RunDayBucket = {
  key: string;
  label: string;
  runs: number;
  complete: number;
  failed: number;
  cards: number;
  alerts: number;
};

export type DeliveryTarget = {
  schema_version: "delivery_target_v1";
  target_id: string;
  type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  display_name?: string;
  status_label?: string;
  detail?: string;
  updated_at: string;
};

export type DeliveryTestResult = {
  schema_version: "desk_delivery_test_result_v1";
  target_id: string;
  target_type: string;
  mode: "dry-run" | "live";
  ok: boolean;
  status: string;
  title?: string;
  detail?: string;
  error?: string;
  finished_at?: string;
};

export type DeliveryChatDetectionResult = {
  schema_version: "desk_delivery_chat_detection_v1";
  target_id: string;
  target_type: string;
  ok: boolean;
  status: string;
  source: string;
  chat_id: string;
  chat_type: string;
  title?: string;
  detail?: string;
  finished_at?: string;
};

export type ProfilePatch = {
  patch_id: string;
  profile_id: string;
  profile_display_path?: string;
  card_id?: string;
  card_title?: string;
  note: string;
  status: string;
  diff_text: string;
  base_profile_hash?: string;
  base_profile_short_hash?: string;
  replayed_from_patch_id?: string;
  duplicate_patch_count?: number;
  source_card_count?: number;
  source_card_titles?: string[];
  apply_readiness?: {
    status?: string;
    label?: string;
    detail?: string;
  };
  created_at: string;
  applied_at?: string;
};

export type DashboardState = {
  schema_version?: "dashboard_state_v1";
  profiles: Profile[];
  inbox: ReviewCard[];
  runs: Run[];
  delivery_targets: DeliveryTarget[];
  profile_patch_suggestions: ProfilePatch[];
  source_stats: SourceStat[];
  source_insights: SourceInsight[];
  feedback_summary?: {
    schema_version?: "dashboard_feedback_summary_v1" | "dashboard_feedback_summary_v2";
    current_decision_count?: number;
    exportable_count?: number;
    changed_since_last_export?: boolean;
    last_export_path?: string;
    non_exportable_follow_up_count?: number;
    profile_diff_count?: number;
    pending_profile_diff_count?: number;
    applied_profile_diff_count?: number;
    reverted_profile_diff_count?: number;
    export_scope_note?: string;
    next_action?: DashboardNextAction;
    recent_impacts?: FeedbackImpact[];
    calibration?: FeedbackCalibrationSummary;
    by_action?: Record<string, number>;
    by_rating?: Record<string, number>;
    by_decision_status?: Record<string, number>;
  };
  opportunity_summary?: OpportunitySummary;
  validation_summary?: ValidationSummary;
  active_actions?: DeskActiveAction[];
  setup_status?: {
    schema_version?: "dashboard_setup_status_v1";
    stage?: string;
    next_step?: string;
    has_profiles?: boolean;
    has_runs?: boolean;
    has_delivery_targets?: boolean;
    has_enabled_delivery_targets?: boolean;
    checks?: SetupCheck[];
  };
};

export type ValidationSummary = {
  schema_version?: "dashboard_validation_summary_v1";
  window_days?: number;
  since?: string;
  runs_count?: number;
  card_count?: number;
  high_card_count?: number;
  pending_count?: number;
  action_count?: number;
  by_action?: Record<string, number>;
  triage_rate?: number;
  keep_rate?: number;
  false_positive_rate?: number;
  first_decision_minutes?: number;
  first_decision_action?: string;
  next_action?: {
    label?: string;
    detail?: string;
    command?: string;
  };
};

export type OpportunitySummaryItem = {
  card_id: string;
  title: string;
  rating: string;
  decision_status: string;
  status: string;
  why?: string;
  source_refs?: SourceRef[];
  updated_at?: string;
};

export type OpportunitySummary = {
  schema_version?: "dashboard_opportunity_summary_v1";
  status?: string;
  run_id?: string;
  profile_id?: string;
  display_name?: string;
  scanned_count?: number;
  matched_count?: number;
  review_card_count?: number;
  alert_count?: number;
  high_actionable_count?: number;
  all_clear?: boolean;
  top_items?: OpportunitySummaryItem[];
  diagnostics?: {
    failure_count?: number;
    warning_count?: number;
    top_code?: string;
  };
  decision_counts?: Record<string, number>;
  next_action?: {
    label?: string;
    detail?: string;
    command?: string;
  };
};

export type SetupCheck = {
  check_id: string;
  label: string;
  status: "done" | "active" | "blocked" | "todo" | string;
  detail?: string;
  command?: string;
  source_access?: DeskActionResult["source_access"];
};

export type DeskActionRunMode = "execute" | "confirm_execute" | "needs_human" | string;

export type DeskAction = {
  schema_version: "desk_action_v1";
  action_id: string;
  group: string;
  title: string;
  detail: string;
  run_mode: DeskActionRunMode;
  display_command: string;
  next_action: string;
};

export type DeskActionStatus = "success" | "failed" | "needs_human" | "blocked" | string;

export type DeskActionResult = {
  schema_version: "desk_action_result_v1";
  action_id: string;
  status: DeskActionStatus;
  title: string;
  detail: string;
  display_command: string;
  exit_code: number | null;
  artifact_path: string;
  next_action: string;
  finished_at: string;
  source_access?: {
    schema_version?: "desk_source_access_health_v1";
    checked_at?: string;
    source_count: number;
    checked_count: number;
    accessible_count: number;
    quiet_count: number;
    inaccessible_count: number;
    truncated_count: number;
    probe_window_hours?: number;
    probe_window_hours_min?: number;
    probe_window_hours_max?: number;
    reason_counts?: Record<string, number>;
  };
};

export type DeskActiveAction = {
  schema_version?: "desk_active_action_v1";
  action_id: string;
  title: string;
  status: string;
  started_at: string;
  updated_at?: string;
  elapsed_seconds?: number;
  checked_count?: number;
  total_count?: number;
  detail?: string;
};

export type DeskSchedulerStatus = {
  schema_version: "desk_scheduler_status_v1";
  available: boolean;
  installed: boolean;
  status: string;
  task_label: string;
  profile_id?: string;
  interval_minutes: number;
  platform?: string;
  backend?: string;
  can_install?: boolean;
  can_remove?: boolean;
  display_command?: string;
  last_exit_code?: number;
  detail: string;
  next_action: string;
  checked_at: string;
};

export type DeskTelegramStatus = {
  schema_version: "desk_telegram_status_v1";
  credentials_ready: boolean;
  credentials_status?: string;
  session_ready: boolean;
  login_state: string;
  detail: string;
  next_step: string;
  config_path: string;
  session_path: string;
};

export type Tab = "inbox" | "actions" | "profiles" | "runs" | "settings";

export type Metric = {
  label: string;
  value: string;
  detail: string;
  tone: "amber" | "teal" | "rust" | "blue";
  meter?: number;
};

export type GitUpdateStatus = {
  schema_version: "git_update_status_v1";
  status: string;
  message: string;
  branch: string;
  upstream?: string | null;
  repo_url?: string | null;
  head?: string | null;
  remote_head?: string | null;
  ahead: number;
  behind: number;
  dirty: boolean;
  dirty_count: number;
  dirty_paths?: string[];
  repairable_dirty?: boolean;
  repairable_dirty_count?: number;
  dirty_repair_applied?: boolean;
  pull_allowed: boolean;
  checked_at: string;
  fetched?: boolean;
  pull_output?: string;
  desk_build_status?: "success" | "failed" | "skipped";
  desk_build_message?: string;
  desk_reload_recommended?: boolean;
};

export type FeedbackExportResult = {
  schema_version: "feedback_export_result_v1";
  feedback_count: number;
  output_path: string;
  changed_since_last_export?: boolean;
  exported_at?: string;
};

export type FeedbackProfileSuggestionsResult = {
  schema_version: "feedback_profile_suggestions_result_v1";
  created_count: number;
  existing_count: number;
  skipped_count: number;
  patch_ids: string[];
  profile_ids: string[];
  detail?: string;
  generated_at?: string;
};

export type FeedbackClearResult = {
  schema_version: "feedback_clear_result_v1";
  cleared_count: number;
};

export type ProfileTemplate = {
  id: string;
  title: string;
  audience: string;
  default_topic: string;
  starter_brief: string;
  coach_questions: string[];
  supported_fields: string[];
};

export type ProfileTemplateCatalog = {
  schema_version: "desk_profile_template_catalog_v1";
  templates: ProfileTemplate[];
};

export type ProfileCreatePreview = {
  schema_version: "desk_profile_create_preview_v1";
  status: "ready" | "needs_input" | string;
  template_id: string;
  title: string;
  topic: string;
  questions: string[];
  generated_rules: string[];
  search_rules: string[];
  rejection_rules: string[];
  keywords: string[];
  markdown_preview: string;
  warnings: string[];
  llm_used: boolean;
};

export type ProfileCoachPreview = {
  schema_version: "profile_coach_preview_v1";
  status: "ready" | "needs_evidence" | string;
  profile_id: string;
  stage?: string;
  evidence_counts: Record<string, number>;
  diagnosis: Array<{ label: string; detail: string }>;
  suspected_false_positive_patterns: string[];
  suggested_preference_rules: string[];
  source_suggestions: Array<{ kind: string; label: string; detail: string }>;
  confidence: string;
  warnings: string[];
  llm_used: boolean;
};

export type ProfileCreateResult = {
  schema_version: "desk_profile_create_result_v1";
  profile_id: string;
  display_name: string;
  profile_path: string;
  created: boolean;
  detail: string;
  next_action: string;
  created_at?: string;
};
