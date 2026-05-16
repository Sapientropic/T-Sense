import { describe, expect, it } from "vitest";

import {
  sanitizeDeskSourcesResult,
  sanitizeDeliveryChatDetectionResult,
  sanitizeDeliveryTestResult,
  sanitizeSourceImportResult,
} from "./sanitize";

describe("Desk source and delivery sanitizers", () => {
  it("sanitizes notification test result envelopes without hiding live sends", () => {
    expect(
      sanitizeDeliveryTestResult({
        schema_version: "desk_delivery_test_result_v1",
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        mode: "live",
        ok: true,
        status: "sent",
        title: "Notification test",
        detail: "Checked",
      }),
    ).toEqual({
      schema_version: "desk_delivery_test_result_v1",
      target_id: "telegram-bot-default",
      target_type: "telegram_bot",
      mode: "live",
      ok: true,
      status: "sent",
      title: "Notification test",
      detail: "Checked",
    });
    expect(sanitizeDeliveryTestResult({ target_id: "telegram-bot-default", target_type: "telegram_bot" })).toBeNull();
    expect(
      sanitizeDeliveryTestResult({
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "dry_run",
      }),
    ).toBeNull();
    expect(
      sanitizeDeliveryChatDetectionResult({
        schema_version: "desk_delivery_chat_detection_v1",
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
        chat_id: "123456",
        chat_type: "private",
        title: "Detected chat",
      }),
    ).toEqual({
      schema_version: "desk_delivery_chat_detection_v1",
      target_id: "telegram-bot-default",
      target_type: "telegram_bot",
      ok: true,
      status: "detected",
      source: "updates",
      chat_id: "123456",
      chat_type: "private",
      title: "Detected chat",
    });
    expect(
      sanitizeDeliveryChatDetectionResult({
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
      }),
    ).toBeNull();
  });

  it("sanitizes source import result envelopes without trusting backend-only fields", () => {
    expect(
      sanitizeSourceImportResult({
        schema_version: "desk_source_import_result_v1",
        dry_run: true,
        written: false,
        topic: " jobs ",
        added_count: 2,
        updated_count: 1,
        unchanged_count: -4,
        source_count: 3,
        registry_path: " .tgcs/sources.json ",
        preview_truncated_count: 8,
        preview_sources: [
          { label: " remote_jobs ", source_id: " telegram:remote_jobs ", token: "secret" },
          { label: "", source_id: "bad" },
        ],
        resolved_plan: {
          add: [" remote_jobs ", 12],
          remove: [" telegram:old_jobs "],
          disable: [" telegram:spam_jobs "],
          enable: [" telegram:paused_jobs "],
        },
        title: " Source preview ready ",
        detail: " Review first. ",
        command: "tgcs sources import private.txt",
      }),
    ).toEqual({
      schema_version: "desk_source_import_result_v1",
      dry_run: true,
      written: false,
      topic: "jobs",
      added_count: 2,
      updated_count: 1,
      unchanged_count: 0,
      removed_count: 0,
      enabled_count: 0,
      disabled_count: 0,
      source_count: 3,
      registry_path: ".tgcs/sources.json",
      preview_sources: [{ label: "remote_jobs", source_id: "telegram:remote_jobs" }],
      resolved_plan: {
        add: ["remote_jobs"],
        remove: ["telegram:old_jobs"],
        disable: ["telegram:spam_jobs"],
        enable: ["telegram:paused_jobs"],
      },
      preview_truncated_count: 8,
      action: undefined,
      llm_used: false,
      title: "Source preview ready",
      detail: "Review first.",
      next_action: undefined,
      finished_at: undefined,
    });
    expect(sanitizeSourceImportResult({ topic: "jobs" })).toBeNull();
  });

  it("sanitizes saved source library envelopes without leaking backend-only fields", () => {
    expect(
      sanitizeDeskSourcesResult({
        schema_version: "desk_sources_v1",
        source_count: 2,
        enabled_count: 1,
        topics: [" jobs ", 7, "ai"],
        registry_path: " .tgcs/sources.json ",
        sources: [
          {
            schema_version: "desk_source_v1",
            source_id: " telegram:remote_jobs ",
            label: " Remote Jobs ",
            channel: " remote_jobs ",
            enabled: true,
            topics: ["jobs", "", 42],
            priority: " high ",
            scan_window_hours: 48,
            token: "secret",
            command: "tgcs sources import private.txt",
          },
          {
            source_id: "telegram:quiet_jobs",
            label: "Quiet Jobs",
            channel: "quiet_jobs",
            enabled: false,
            topics: "jobs",
            priority: 2,
            scan_window_hours: -1,
          },
          { source_id: "bad", label: "", channel: "broken" },
        ],
      }),
    ).toEqual({
      schema_version: "desk_sources_v1",
      source_count: 2,
      enabled_count: 1,
      topics: ["jobs", "ai"],
      registry_path: ".tgcs/sources.json",
      sources: [
        {
          schema_version: "desk_source_v1",
          source_id: "telegram:remote_jobs",
          label: "Remote Jobs",
          channel: "remote_jobs",
          enabled: true,
          topics: ["jobs"],
          priority: "high",
          scan_window_hours: 48,
        },
        {
          schema_version: undefined,
          source_id: "telegram:quiet_jobs",
          label: "Quiet Jobs",
          channel: "quiet_jobs",
          enabled: false,
          topics: [],
          priority: "normal",
          scan_window_hours: 24,
        },
      ],
    });
    expect(JSON.stringify(sanitizeDeskSourcesResult({ registry_path: ".tgcs/sources.json", sources: [] }))).not.toContain("secret");
    expect(sanitizeDeskSourcesResult({ sources: [] })).toBeNull();
  });
});
