import { createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  SOURCE_LIBRARY_PAGE_SIZE,
  botIdentityResultLine,
  botGatewayBackgroundLine,
  botGatewayCanInstallBackground,
  botGatewayLivenessLine,
  botGatewayRepairLabel,
  botGatewayStatusLine,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
  sourceTopicsEditState,
} from "./settings";
import { NotificationsPanel } from "./settings/notifications-panel";
import { BotGatewayPanel, settingsMiniAppUrlState } from "./settings/bot-gateway-panel";
import { DeliveryTargetEditor } from "./settings/delivery-target-editor";
import { LearningPanel } from "./settings/learning-panel";
import { SourceImportPanel } from "./settings/source-import-panel";
import { SourceInsightsPanel } from "./settings/source-insights-panel";
import { SourceLibraryRow } from "./settings/source-library-row";
import { SettingsTaskSwitch } from "./settings/task-switch";
import { SupportPanel, supportSummary } from "./settings/support-panel";
import type {
  DeliveryTarget,
  DeskBotIdentityResult,
  DeskBotGatewayStatus,
  DeskSource,
  DeskSupportStatus,
  Profile,
  ProfileCoachPreview,
  SourceStat,
} from "../domain/types";

function source(overrides: Partial<DeskSource>): DeskSource {
  return {
    source_id: "telegram:remote_jobs",
    label: "remote_jobs",
    channel: "remote_jobs",
    enabled: true,
    topics: ["jobs"],
    priority: "normal",
    scan_window_hours: 24,
    ...overrides,
  };
}

function sourceStat(overrides: Partial<SourceStat>): SourceStat {
  return {
    channel: "remote_jobs",
    card_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    pending_count: 0,
    handled_count: 0,
    false_positive_count: 0,
    alert_count: 0,
    high_rate: 0,
    ...overrides,
  };
}

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    profile_id: "ai-roles",
    display_name: "AI Roles",
    enabled: true,
    source_topics: ["ai-roles"],
    updated_at: "2026-05-14T00:00:00Z",
    ...overrides,
  };
}

function deliveryTarget(overrides: Partial<DeliveryTarget> = {}): DeliveryTarget {
  return {
    schema_version: "delivery_target_v1",
    target_id: "telegram-bot-default",
    type: "telegram_bot",
    enabled: false,
    config: { chat_id: "@desk_signal" },
    display_name: "Telegram Bot",
    status_label: "Muted",
    detail: "Delivery is muted.",
    updated_at: "2026-05-14T00:00:00Z",
    ...overrides,
  };
}

function supportStatus(overrides: Partial<DeskSupportStatus> = {}): DeskSupportStatus {
  return {
    schema_version: "desk_support_status_v1",
    app_data_root: "/Users/example/Library/Application Support/T-Sense",
    code_root: "/Applications/T-Sense.app/Contents/Resources",
    database_path: "/Users/example/Library/Application Support/T-Sense/.tgcs/tgcs.db",
    output_dir: "/Users/example/Library/Application Support/T-Sense/output",
    source_registry_path: "/Users/example/Library/Application Support/T-Sense/.tgcs/sources.json",
    telegram_config_dir: "/Users/example/Library/Application Support/T-Sense/.tgcs/telegram",
    desktop_log_path: "/Users/example/Library/Logs/T-Sense/desktop-backend.log",
    dashboard_url: "http://127.0.0.1:8766",
    platform: "macOS-15.0-arm64",
    checked_at: "2026-05-16T14:00:00Z",
    paths: [
      {
        label: "Local data",
        path: "/Users/example/Library/Application Support/T-Sense",
        target: "app_data_root",
        exists: true,
        detail: "Profiles, sources, database, Telegram session, reports, and review choices live here.",
      },
      {
        label: "Backend log",
        path: "/Users/example/Library/Logs/T-Sense/desktop-backend.log",
        target: "desktop_log",
        exists: true,
        detail: "Desktop launch and backend stderr.",
      },
    ],
    data_boundaries: [
      {
        label: "Local state",
        detail: "Profiles, source lists, review decisions, reports, and Telegram sessions stay on this Mac by default.",
        external: false,
      },
      {
        label: "AI requests",
        detail: "Selected scan text can be sent to the chosen AI provider.",
        external: true,
      },
    ],
    recovery: [
      {
        label: "Backend will not start",
        detail: "Check the backend log first.",
        path: "/Users/example/Library/Logs/T-Sense/desktop-backend.log",
      },
    ],
    readiness: {
      schema_version: "desk_support_readiness_v1",
      status: "needs_user",
      ready_count: 2,
      total_count: 5,
      summary: "2/5 real-scan checks ready.",
      items: [
        {
          label: "Demo report",
          status: "ready",
          detail: "A local sample report is available.",
        },
        {
          label: "Telegram login",
          status: "needs_user",
          detail: "Telegram is not fully authorized on this Mac yet.",
          next_action: "Finish Telegram setup before scanning private sources.",
        },
      ],
    },
    migration: {
      schema_version: "desk_support_migration_v1",
      status: "no_legacy_data",
      detail: "No legacy project-local data was found from this app context.",
      next_action: "No migration action is needed.",
      legacy_locations: [],
    },
    ...overrides,
  };
}

describe("Settings source topic editor", () => {
  it("keeps updates and diagnostics behind the Advanced settings disclosure", () => {
    const html = renderToStaticMarkup(
      <SettingsTaskSwitch
        activeTask="sources"
        aiCount={1}
        feedbackCount={0}
        notificationCount={0}
        onSelect={() => undefined}
        sourceCount={3}
        supportCount={2}
        updateCount={0}
      />,
    );

    expect(html).toContain("Sources");
    expect(html).toContain("AI API");
    expect(html).toContain("Alerts");
    expect(html).toContain("Learning");
    expect(html).toContain("<summary><span>Advanced</span>");
    expect(html).toContain("Updates");
    expect(html).toContain("Help");
    expect(html).not.toContain("open=\"\"");
  });

  it("opens Advanced settings when a support shortcut is selected", () => {
    const html = renderToStaticMarkup(
      <SettingsTaskSwitch
        activeTask="support"
        aiCount={1}
        feedbackCount={0}
        notificationCount={0}
        onSelect={() => undefined}
        sourceCount={3}
        supportCount={2}
        updateCount={0}
      />,
    );

    expect(html).toContain("<details class=\"settings-advanced-switch\" open=\"\">");
    expect(html).toContain("aria-pressed=\"true\"");
    expect(html).toContain("Diagnostics and recovery");
  });

  it("normalizes and validates source topic edits", () => {
    expect(sourceTopicsEditState(["jobs"], "jobs")).toMatchObject({ canSave: false, topics: ["jobs"] });
    expect(sourceTopicsEditState(["jobs"], " Remote-Work, jobs, remote-work ")).toMatchObject({
      canSave: true,
      topics: ["remote-work", "jobs"],
    });
    expect(sourceTopicsEditState(["jobs"], "jobs\nremote-work")).toMatchObject({
      canSave: true,
      topics: ["jobs", "remote-work"],
    });
    expect(sourceTopicsEditState(["jobs"], " ")).toMatchObject({ canSave: false, topics: [] });
    expect(sourceTopicsEditState(["jobs"], "../private")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "x")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "-jobs")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "_jobs")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "工作")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], `a${"b".repeat(41)}`)).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "jobs, 123")).toMatchObject({ canSave: true, topics: ["jobs", "123"] });
  });

  it("limits topic count", () => {
    const text = Array.from({ length: 9 }, (_, index) => `topic${index}`).join(", ");

    expect(sourceTopicsEditState(["jobs"], text)).toMatchObject({ canSave: false });
  });

  it("filters saved sources by topic chips or search text", () => {
    const sources = [
      source({ source_id: "telegram:remote_jobs", label: "Remote Jobs", topics: ["jobs", "remote-work"] }),
      source({ source_id: "telegram:market_news", label: "Market News", channel: "market_news", topics: ["jobs", "market-news"] }),
      source({
        source_id: "telegram:public_catalog",
        label: "Public Catalog",
        channel: "public_catalog",
        notes: "Recommended via public catalog",
      } as Partial<DeskSource>),
    ];

    expect(filterDeskSourcesByQuery(sources, "", "remote-work").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
    ]);
    expect(filterDeskSourcesByQuery(sources, "market").map((item) => item.source_id)).toEqual([
      "telegram:market_news",
    ]);
    expect(filterDeskSourcesByQuery(sources, "news", "jobs").map((item) => item.source_id)).toEqual([
      "telegram:market_news",
    ]);
    expect(filterDeskSourcesByQuery(sources, "rem", "jobs").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
    ]);
    expect(filterDeskSourcesByQuery(sources, "public catalog").map((item) => item.source_id)).toEqual([
      "telegram:public_catalog",
    ]);
    expect(filterDeskSourcesByQuery(sources, " ", " ").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
      "telegram:market_news",
      "telegram:public_catalog",
    ]);
  });

  it("renders imported public-source metadata in saved source rows", () => {
    const html = renderToStaticMarkup(
      <SourceLibraryRow
        busy={false}
        removeSource={async () => undefined}
        setSourceEnabled={async () => undefined}
        setSourceTopics={async () => undefined}
        source={source({
          label: "Remote Jobs",
          expected_language: "en",
          notes: "Recommended via public catalog",
        } as Partial<DeskSource>)}
      />,
    );

    expect(html).toContain("Remote Jobs");
    expect(html).toContain("Lang en");
    expect(html).toContain("Recommended via public catalog");
  });

  it("turns raw public-source recommendation notes into a readable row summary", () => {
    const notes = [
      "Recommended via public Telegram page checked 2026-05-17",
      "Broad public seed. Review and prune aggressively if it creates low-signal cards.",
      "direct_page_status: 200",
      "expected_noise: high",
      "has_public_messages: True",
      "scope: worldwide remote jobs",
    ].join("; ");
    const html = renderToStaticMarkup(
      <SourceLibraryRow
        busy={false}
        removeSource={async () => undefined}
        setSourceEnabled={async () => undefined}
        setSourceTopics={async () => undefined}
        source={source({
          label: "Remote Jobs",
          expected_language: "en",
          notes,
        } as Partial<DeskSource>)}
      />,
    );

    expect(html).toContain("Recommended via public Telegram page checked 2026-05-17");
    expect(html).toContain("Noise high");
    expect(html).toContain("worldwide remote jobs");
    expect(html).not.toContain(">direct_page_status");
    expect(html).not.toContain(">has_public_messages");
  });

  it("defaults saved source rendering to the first page", () => {
    const sources = Array.from({ length: SOURCE_LIBRARY_PAGE_SIZE + 3 }, (_, index) =>
      source({ source_id: `telegram:source_${index}`, label: `Source ${index}`, channel: `source_${index}` }),
    );

    expect(paginatedDeskSources(sources).map((item) => item.source_id)).toHaveLength(SOURCE_LIBRARY_PAGE_SIZE);
    expect(paginatedDeskSources(sources, SOURCE_LIBRARY_PAGE_SIZE + 24)).toHaveLength(SOURCE_LIBRARY_PAGE_SIZE + 3);
  });

  it("labels source counts as pagination or matching state", () => {
    expect(sourceLibraryCountLabel(8, 82, false)).toBe("Showing first 8 of 82");
    expect(sourceLibraryCountLabel(12, 12, false)).toBe("Showing all 12");
    expect(sourceLibraryCountLabel(4, 4, true)).toBe("4 matching shown");
    expect(sourceLibraryCountLabel(8, 82, true)).toBe("8 of 82 matching shown");
    expect(sourceLibraryCountLabel(0, 0, true)).toBe("No matching sources");
  });

  it("summarizes saved source yield from existing stats only", () => {
    expect(sourceLibraryActivityLabel([
      sourceStat({ latest_card_count: 2, alert_count: 1 }),
      sourceStat({ channel: "quiet" }),
      sourceStat({ channel: "risk", scan_incomplete: true }),
    ])).toBe("2 latest cards · 1 alert · 3 tracked · 1 risk");
    expect(sourceLibraryActivityLabel([])).toBe("");
  });

  it("turns source stats into source recommendations with real next-step buttons", () => {
    const html = renderToStaticMarkup(
      <SourceInsightsPanel
        onManageSources={() => undefined}
        onReviewCards={() => undefined}
        sourceStats={[
          sourceStat({
            display_name: "Remote Jobs",
            card_count: 4,
            high_count: 2,
            latest_card_count: 1,
          }),
        ]}
        sourceInsights={[
          {
            kind: "promote",
            channel: "remote_jobs",
            label: "Promote",
            reason: "High signal source.",
            priority: 1,
            stats: sourceStat({ high_count: 2 }),
          },
        ]}
      />,
    );

    expect(html).toContain("Source recommendations");
    expect(html).toContain("<details class=\"table-section source-recommendations-panel\"");
    expect(html).toContain("<summary");
    expect(html).toContain("Remote Jobs");
    expect(html).toContain("Review cards");
    expect(html).toContain("Manage sources");
    expect(html).not.toContain("Yield History");
    expect(html).not.toContain("Source Actions");
    expect(html).not.toContain("Source yield details");
    expect(html).not.toContain("Source action details");
  });

  it("frames source setup as Telegram discovery plus public link and starter recommendation paths", () => {
    const html = renderToStaticMarkup(
      <SourceImportPanel
        result={null}
        previewSourceImport={async () => {
          throw new Error("manual import should not be the primary flow");
        }}
        importSources={async () => {
          throw new Error("manual import should not be the primary flow");
        }}
        importStarterSources={async () => {
          throw new Error("starter import should not be the primary flow");
        }}
        previewSourceAssistant={async () => ({
          dry_run: true,
          written: false,
          topic: "ai-roles",
          added_count: 0,
          updated_count: 0,
          unchanged_count: 0,
          source_count: 0,
          registry_path: ".tgcs/sources.json",
          preview_sources: [],
          preview_truncated_count: 0,
        })}
        applySourceAssistant={async () => ({
          dry_run: false,
          written: true,
          topic: "ai-roles",
          added_count: 0,
          updated_count: 0,
          unchanged_count: 0,
          source_count: 0,
          registry_path: ".tgcs/sources.json",
          preview_sources: [],
          preview_truncated_count: 0,
        })}
        busy={false}
        hasSavedSources={false}
        profiles={[profile()]}
      />,
    );

    expect(html).toContain("Discover Sources");
    expect(html).toContain("AI filters your Telegram channels against the selected profile.");
    expect(html).toContain("Telegram folder");
    expect(html).toContain("All channels");
    expect(html).toContain("Folder ID");
    expect(html).toContain("Public links or candidate JSON");
    expect(html).toContain("public_source_candidates_v1 JSON");
    expect(html).toContain("Preview links");
    expect(html).toContain("Add links");
    expect(html).toContain("Starter recommendations");
    expect(html).toContain("aria-pressed=\"true\"");
    expect(html).not.toContain("readOnly");
    expect(html).not.toContain("readonly");
  });

  it("puts starter and public source paths before AI discovery when no profile exists", () => {
    const html = renderToStaticMarkup(
      <SourceImportPanel
        result={null}
        previewSourceImport={async () => {
          throw new Error("manual import should not run during render");
        }}
        importSources={async () => {
          throw new Error("manual import should not run during render");
        }}
        importStarterSources={async () => {
          throw new Error("starter import should not run during render");
        }}
        previewSourceAssistant={async () => {
          throw new Error("assistant should not run during render");
        }}
        applySourceAssistant={async () => {
          throw new Error("assistant should not run during render");
        }}
        busy={false}
        hasSavedSources={false}
        profiles={[]}
      />,
    );

    expect(html).toContain("Known public sources");
    expect(html).toContain("Starter recommendations");
    expect(html).toContain("Create a profile to unlock AI Telegram folder discovery.");
    expect(html.indexOf("Known public sources")).toBeLessThan(html.indexOf("Create a profile to unlock AI Telegram folder discovery."));
    expect(html).not.toContain("AI filters your Telegram channels against the selected profile.");
    expect(html).not.toContain("value=\"default\"");
    expect(html).not.toContain("Profile</span><select");
  });

  it("shows profile coach confidence and matching mode after preview", () => {
    const coach: ProfileCoachPreview = {
      schema_version: "profile_coach_preview_v1",
      status: "ready",
      profile_id: "ai-roles",
      evidence_counts: { keep: 1, skip: 1, false_positive: 1, follow_up: 1 },
      diagnosis: [{ label: "Clearer boundaries", detail: "Keep and skip choices can sharpen matching." }],
      suspected_false_positive_patterns: [],
      suggested_preference_rules: ["Down-rank recurring wrong-match patterns."],
      source_suggestions: [],
      confidence: "medium",
      warnings: [],
      llm_used: true,
    };
    const html = renderToStaticMarkup(
      <LearningPanel
        busy={false}
        clearFeedback={() => undefined}
        createProfileMatchingPreferencesDraft={() => undefined}
        exportFeedback={() => undefined}
        exportResult={null}
        generateProfileSuggestions={() => undefined}
        openProfileDrafts={() => undefined}
        openReviewCards={() => undefined}
        previewProfileCoach={() => undefined}
        profileCoachPreview={coach}
        profiles={[profile()]}
        runAgainWithLearning={() => undefined}
        suggestionResult={null}
        summary={{
          schema_version: "dashboard_feedback_summary_v2",
          current_decision_count: 4,
          exportable_count: 3,
          by_action: { keep: 1, skip: 1, false_positive: 1 },
          non_exportable_follow_up_count: 1,
        }}
        undoFeedbackDecision={() => undefined}
      />,
    );

    expect(html).toContain("Coach matching mode");
    expect(html).toContain("Confidence medium");
    expect(html).toContain("Smart suggestions");
  });

  it("keeps source refresh guidance behind a closed disclosure after sources exist", () => {
    const html = renderToStaticMarkup(
      <SourceImportPanel
        result={null}
        previewSourceImport={async () => {
          throw new Error("manual import should not be the primary flow");
        }}
        importSources={async () => {
          throw new Error("manual import should not be the primary flow");
        }}
        importStarterSources={async () => {
          throw new Error("starter import should not be the primary flow");
        }}
        previewSourceAssistant={async () => ({
          dry_run: true,
          written: false,
          topic: "ai-roles",
          added_count: 0,
          updated_count: 0,
          unchanged_count: 0,
          source_count: 0,
          registry_path: ".tgcs/sources.json",
          preview_sources: [],
          preview_truncated_count: 0,
        })}
        applySourceAssistant={async () => ({
          dry_run: false,
          written: true,
          topic: "ai-roles",
          added_count: 0,
          updated_count: 0,
          unchanged_count: 0,
          source_count: 0,
          registry_path: ".tgcs/sources.json",
          preview_sources: [],
          preview_truncated_count: 0,
        })}
        busy={false}
        hasSavedSources={true}
        profiles={[profile()]}
      />,
    );

    expect(html).toContain("<details class=\"table-section source-import-panel source-import-details\">");
    expect(html).toContain("Discover Sources");
    expect(html).toContain("AI filters your Telegram channels against the selected profile.");
    expect(html).not.toContain("Open when refreshing the AI-selected list");
  });

  it("keeps notification target checks free of dry-run wording", () => {
    const html = renderToStaticMarkup(
      <DeliveryTargetEditor
        busy={false}
        detectionResult={null}
        detectDeliveryChatId={async () => ({
          schema_version: "desk_delivery_chat_detection_v1",
          ok: false,
          target_id: "telegram-bot-default",
          target_type: "telegram_bot",
          status: "missing",
          source: "updates",
          title: "No chat found",
          detail: "Send a message first.",
          chat_id: "",
          chat_type: "",
        })}
        saveDeliveryTarget={async () => undefined}
        target={deliveryTarget()}
        testDeliveryTarget={async () => undefined}
        testResult={null}
      />,
    );

    expect(html).toContain("Send test message");
    expect(html).toContain("Sends a Telegram message to this chat");
    expect(html).not.toContain("dry run");
    expect(html).not.toContain("dry-run");
  });

  it("summarizes Bot Gateway readiness without exposing identifiers", () => {
    const status: DeskBotGatewayStatus = {
      schema_version: "desk_bot_gateway_status_v1",
      token_configured: true,
      authorized_chat_count: 1,
      gateway_status: "running",
      commands_installed: true,
      supported_commands: ["/status", "/latest", "/scan"],
      local_first_note: "Bot replies only while tgcs bot run is running locally.",
      start_command: "./tgcs bot run",
      background: {
        schema_version: "desk_bot_gateway_background_status_v1",
        backend: "windows_schtasks",
        available: true,
        installed: true,
        status: "installed",
        can_install: false,
        can_remove: true,
        detail: "Background mode is on.",
        next_action: "Leave Signal Desk closed.",
      },
    };

    expect(botGatewayStatusLine(status)).toBe("Running · token ready · 1 chat");
    expect(botGatewayLivenessLine(status)).toBe("Bot is running");
    expect(botGatewayLivenessLine({ ...status, gateway_status: "stale" })).toBe("Bot may be stopped");
    expect(botGatewayRepairLabel({ ...status, gateway_status: "stale" })).toBe("Repair alerts");
    expect(botGatewayStatusLine({ ...status, authorized_chat_count: 0, gateway_status: "not_detected" })).toBe(
      "Not detected · token ready · no chats",
    );
    expect(botGatewayBackgroundLine(status)).toBe("Background on · Windows Task Scheduler");
    expect(botGatewayBackgroundLine({ ...status, token_configured: false })).toBe("Save token before background mode");
    expect(botGatewayBackgroundLine({ ...status, authorized_chat_count: 0, background: { ...status.background, installed: false } })).toBe(
      "Add chat before background mode",
    );
    expect(botGatewayBackgroundLine({ ...status, background: { ...status.background, installed: false } })).toBe(
      "Background off · Windows Task Scheduler",
    );
    expect(botGatewayCanInstallBackground({
      ...status,
      background: { ...status.background, installed: false, can_install: true },
    })).toBe(true);
    expect(botGatewayCanInstallBackground({
      ...status,
      token_configured: false,
      background: { ...status.background, installed: false, can_install: true },
    })).toBe(false);
    expect(botGatewayCanInstallBackground({
      ...status,
      authorized_chat_count: 0,
      background: { ...status.background, installed: false, can_install: true },
    })).toBe(false);
  });

  it("summarizes bot identity apply result with photo boundary", () => {
    const result: DeskBotIdentityResult = {
      schema_version: "bot_identity_apply_result_v1",
      name: "T-Sense",
      description_updated: true,
      short_description_updated: true,
      commands_installed: true,
      profile_photo_updated: false,
    };

    expect(botIdentityResultLine(result)).toBe("T-Sense identity applied · photo pending");
    expect(botIdentityResultLine({ ...result, profile_photo_updated: true })).toBe("T-Sense identity applied · photo updated");
  });

  it("surfaces a low-noise Telegram Mini App launch card from bot settings", () => {
    const status: DeskBotGatewayStatus = {
      schema_version: "desk_bot_gateway_status_v1",
      token_configured: true,
      authorized_chat_count: 1,
      gateway_status: "running",
      commands_installed: true,
      supported_commands: ["/status", "/latest", "/scan"],
      local_first_note: "Bot replies only while tgcs bot run is running locally.",
      start_command: "./tgcs bot run",
      background: {
        schema_version: "desk_bot_gateway_background_status_v1",
        backend: "macos_launchd",
        available: true,
        installed: true,
        status: "installed",
        can_install: false,
        can_remove: true,
        detail: "Background mode is on.",
        next_action: "Leave Signal Desk closed.",
      },
    };

    const html = renderToStaticMarkup(
      <BotGatewayPanel
        applyBotIdentity={async () => undefined}
        busy={false}
        error={null}
        identityResult={null}
        installMiniAppMenu={async (url) => ({
          schema_version: "bot_miniapp_menu_result_v1",
          menu_button_updated: true,
          dry_run: false,
          text: "Review",
          url,
        })}
        installBotGatewayAutostart={async () => undefined}
        removeBotGatewayAutostart={async () => undefined}
        status={status}
      />,
    );

    expect(html).toContain("Telegram Mini App");
    expect(html).toContain("Review in Telegram");
    expect(html).toContain(">Preview<");
    expect(html).toContain("Public Mini App URL");
    expect(html).toContain("Add public link");
    expect(html).toContain("Paste a public https://.../miniapp link");
    expect(html).toContain(">Ready<");
    expect(html).toContain(">Token<");
    expect(html).toContain(">Paste link<");
    expect(html).toContain(">Menu<");
    expect(html).toContain('href="/miniapp"');
    expect(html).not.toContain("Real Telegram entry needs a public HTTPS /miniapp tunnel");
    expect(html).not.toContain("Phone-ready review surface");
    expect(html).not.toContain("Preview the mobile review flow here");
    expect(html).not.toContain("Sound");
    expect(html).not.toContain("--miniapp-only");
    expect(html).not.toContain("install-miniapp-menu");
    expect(html).not.toContain("&lt;public-https&gt;");
    expect(html).not.toContain("setChatMenuButton");
  });

  it("keeps Mini App install states understandable before calling Telegram", () => {
    const status: DeskBotGatewayStatus = {
      schema_version: "desk_bot_gateway_status_v1",
      token_configured: true,
      authorized_chat_count: 1,
      gateway_status: "running",
      commands_installed: true,
      supported_commands: ["/status", "/latest", "/scan"],
      local_first_note: "Bot replies only while tgcs bot run is running locally.",
      start_command: "./tgcs bot run",
      background: {
        schema_version: "desk_bot_gateway_background_status_v1",
        backend: "macos_launchd",
        available: true,
        installed: true,
        status: "installed",
        can_install: false,
        can_remove: true,
        detail: "Background mode is on.",
        next_action: "Leave Signal Desk closed.",
      },
    };

    expect(settingsMiniAppUrlState({ ...status, token_configured: false }, "https://example.com/miniapp")).toMatchObject({
      state: "needs-token",
      canSubmit: false,
    });
    expect(settingsMiniAppUrlState(status, "")).toMatchObject({ state: "empty", canSubmit: false });
    expect(settingsMiniAppUrlState(status, "http://example.com/miniapp")).toMatchObject({
      state: "invalid",
      label: "Use HTTPS",
      canSubmit: false,
    });
    expect(settingsMiniAppUrlState(status, "https://127.0.0.1:8765/miniapp")).toMatchObject({
      state: "local",
      label: "Public link needed",
      canSubmit: false,
    });
    expect(settingsMiniAppUrlState(status, "https://example.com/miniapp")).toMatchObject({
      state: "ready",
      label: "Ready",
      canSubmit: true,
    });
    expect(settingsMiniAppUrlState(status, "https://example.com/miniapp", {
      schema_version: "bot_miniapp_menu_result_v1",
      menu_button_updated: true,
      dry_run: false,
      text: "Review",
      url: "https://example.com/miniapp",
    })).toMatchObject({
      state: "enabled",
      label: "Enabled",
      canSubmit: false,
    });
  });

  it("keeps an editable default notification target when none is saved yet", () => {
    const html = renderToStaticMarkup(
      <NotificationsPanel
        applyBotIdentity={async () => undefined}
        botGatewayError={null}
        botGatewayStatus={null}
        botIdentityResult={null}
        busy={false}
        clearNotificationToken={async () => undefined}
        deliveryChatDetection={null}
        deliveryTest={null}
        detectDeliveryChatId={async () => ({
          schema_version: "desk_delivery_chat_detection_v1",
          target_id: "telegram-bot-default",
          target_type: "telegram_bot",
          ok: true,
          status: "detected",
          source: "telegram_session",
          chat_id: "123456",
          chat_type: "private",
        })}
        installBotGatewayAutostart={async () => undefined}
        installMiniAppMenu={async (url) => ({
          schema_version: "bot_miniapp_menu_result_v1",
          menu_button_updated: true,
          dry_run: false,
          text: "Review",
          url,
        })}
        notificationTokenError={null}
        notificationTokenStatus={null}
        panelRef={createRef<HTMLDivElement>()}
        removeBotGatewayAutostart={async () => undefined}
        saveDeliveryTarget={async () => undefined}
        saveNotificationToken={async () => undefined}
        targets={[]}
        testDeliveryTarget={async () => undefined}
      />,
    );

    expect(html).toContain("Default notification chat");
    expect(html).toContain("Bot status unknown");
    expect(html).toContain("Repair alerts");
    expect(html).toContain("Add a Telegram chat ID to create the default private bot notification target.");
    expect(html).toContain("Telegram chat ID");
    expect(html).toContain("Detect chat ID");
    expect(html).not.toContain("No notification channels set up");
  });

  it("renders support diagnostics with local paths and data boundaries", () => {
    const status = supportStatus();
    const html = renderToStaticMarkup(
      <SupportPanel
        error={null}
        exportResult={null}
        onExportDiagnostics={() => undefined}
        onRevealTarget={() => undefined}
        onRefresh={() => undefined}
        status={status}
      />,
    );

    expect(html).toContain("Support");
    expect(html).toContain("http://127.0.0.1:8766");
    expect(html).toContain("Local data");
    expect(html).toContain("Backend log");
    expect(html).toContain("Ready For Real Scan");
    expect(html).toContain("2/5 real-scan checks ready.");
    expect(html).toContain("Needs setup");
    expect(html).toContain("Finish Telegram setup before scanning private sources.");
    expect(html).toContain("Data Boundaries");
    expect(html).toContain("AI requests");
    expect(html).toContain("External when run");
    expect(html).toContain("Copy path");
    expect(html).toContain("Reveal");
    expect(html).toContain("Open in Finder");
    expect(html).toContain("Copy summary");
    expect(html).toContain("Save snapshot");
    expect(html).not.toContain("Copy command");
    expect(html).not.toContain("123456:SECRET");
    expect(supportSummary(status)).toContain("Desktop log: /Users/example/Library/Logs/T-Sense/desktop-backend.log");
    expect(supportSummary(status)).toContain("Readiness: 2/5 real-scan checks ready.");
  });

  it("renders legacy project data diagnostics without promising automatic migration", () => {
    const status = supportStatus({
      migration: {
        schema_version: "desk_support_migration_v1",
        status: "manual_required",
        detail: "Legacy project data was found outside the app data folder.",
        next_action: "Use a user-selected source folder before migrating.",
        legacy_locations: [
          {
            label: "Legacy reports",
            path: "/Users/example/project/output",
            exists: true,
            detail: "Reports created before the macOS app moved state into Application Support.",
          },
        ],
      },
    });
    const html = renderToStaticMarkup(
      <SupportPanel
        error={null}
        onRevealTarget={() => undefined}
        onRefresh={() => undefined}
        status={status}
      />,
    );

    expect(html).toContain("Legacy Data");
    expect(html).toContain("Legacy reports");
    expect(html).toContain("user-selected");
    expect(html).not.toContain("automatic migration");
  });
});
