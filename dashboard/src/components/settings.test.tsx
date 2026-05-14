import { createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  SOURCE_LIBRARY_PAGE_SIZE,
  botIdentityResultLine,
  botGatewayBackgroundLine,
  botGatewayCanInstallBackground,
  botGatewayStatusLine,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
  sourceTopicsEditState,
} from "./settings";
import { NotificationsPanel } from "./settings/notifications-panel";
import { DeliveryTargetEditor } from "./settings/delivery-target-editor";
import { SourceImportPanel } from "./settings/source-import-panel";
import { SourceInsightsPanel } from "./settings/source-insights-panel";
import type { DeliveryTarget, DeskBotIdentityResult, DeskBotGatewayStatus, DeskSource, Profile, SourceStat } from "../domain/types";

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

describe("Settings source topic editor", () => {
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
    expect(filterDeskSourcesByQuery(sources, " ", " ").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
      "telegram:market_news",
    ]);
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

  it("keeps source evidence panels collapsible", () => {
    const html = renderToStaticMarkup(
      <SourceInsightsPanel
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

    expect(html).toContain("<details");
    expect(html).toContain("Yield History");
    expect(html).toContain("Source Actions");
    expect(html).toContain("Source yield details");
    expect(html).toContain("Source action details");
  });

  it("frames source setup as Telegram discovery plus AI profile filtering, not pasted channels", () => {
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
    expect(html).toContain("Scan all channels");
    expect(html).not.toContain("<span>Telegram channels</span>");
    expect(html).not.toContain("Paste channel handles");
    expect(html).not.toContain("@remote_jobs");
    expect(html).not.toContain("Use starter set");
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

    expect(html).toContain("Test without sending");
    expect(html).toContain("This checks the saved target without sending a Telegram message.");
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
    expect(html).toContain("Add a Telegram chat ID to create the default private bot notification target.");
    expect(html).toContain("Telegram chat ID");
    expect(html).toContain("Detect chat ID");
    expect(html).not.toContain("No notification channels set up");
  });
});
