import { describe, expect, it } from "vitest";

import {
  sanitizeDeskAiSettingsStatus,
  sanitizeDeskBotIdentityResult,
  sanitizeDeskBotGatewayStatus,
  sanitizeDeskNotificationTokenStatus,
  sanitizeDeskSchedulerStatus,
  sanitizeDeskTelegramStatus,
} from "./sanitize";

describe("Desk bot and local settings sanitizers", () => {
  it("sanitizes Bot Gateway status without accepting sensitive fields", () => {
    expect(
      sanitizeDeskBotGatewayStatus({
        schema_version: "desk_bot_gateway_status_v1",
        token_configured: true,
        authorized_chat_count: 2,
        gateway_status: "running",
        commands_installed: true,
        supported_commands: ["/status", "/latest", "/scan", 7],
        local_first_note: "Replies only while local gateway is running.",
        start_command: "./tgcs bot run",
        last_update_at: "2026-05-12T15:00:00Z",
        last_error: "TGCS_TELEGRAM_BOT_TOKEN=[redacted-secret]",
        safe_next_action: "Bot Gateway is running.",
        background: {
          schema_version: "desk_bot_gateway_background_status_v1",
          backend: "windows_schtasks",
          available: true,
          installed: true,
          status: "installed",
          can_install: false,
          can_remove: true,
          detail: "Background mode is on.",
          next_action: "Turn it off from Settings.",
          checked_at: "2026-05-12T15:00:00Z",
          token: "secret",
        },
        token: "secret",
        chat_id: "123456",
      }),
    ).toEqual({
      schema_version: "desk_bot_gateway_status_v1",
      token_configured: true,
      authorized_chat_count: 2,
      gateway_status: "running",
      commands_installed: true,
      supported_commands: ["/status", "/latest", "/scan"],
      local_first_note: "Replies only while local gateway is running.",
      start_command: "./tgcs bot run",
      last_update_at: "2026-05-12T15:00:00Z",
      last_error: "TGCS_TELEGRAM_BOT_TOKEN=[redacted-secret]",
      safe_next_action: "Bot Gateway is running.",
      background: {
        schema_version: "desk_bot_gateway_background_status_v1",
        backend: "windows_schtasks",
        available: true,
        installed: true,
        status: "installed",
        can_install: false,
        can_remove: true,
        detail: "Background mode is on.",
        next_action: "Turn it off from Settings.",
        checked_at: "2026-05-12T15:00:00Z",
      },
    });
    expect(sanitizeDeskBotGatewayStatus({ token_configured: true })).toBeNull();
  });

  it("sanitizes Bot identity apply result without accepting transport fields", () => {
    expect(
      sanitizeDeskBotIdentityResult({
        schema_version: "bot_identity_apply_result_v1",
        name: "T-Sense",
        description_updated: true,
        short_description_updated: true,
        commands_installed: true,
        profile_photo_updated: false,
        token: "secret",
        chat_id: "123456",
      }),
    ).toEqual({
      schema_version: "bot_identity_apply_result_v1",
      name: "T-Sense",
      description_updated: true,
      short_description_updated: true,
      commands_installed: true,
      profile_photo_updated: false,
    });
    expect(sanitizeDeskBotIdentityResult({ schema_version: "bot_identity_apply_result_v1" })).toBeNull();
  });

  it("sanitizes AI API provider status without exposing secrets", () => {
    expect(
      sanitizeDeskAiSettingsStatus({
        schema_version: "desk_ai_settings_status_v1",
        configured_count: 1,
        local_store_supported: true,
        platform: "win32",
        detail: "1 AI provider key configured.",
        checked_at: "2026-05-11T00:00:00Z",
        providers: [
          {
            provider: "deepseek",
            label: "DeepSeek",
            env_name: "DEEPSEEK_API_KEY",
            configured: true,
            source: "windows_credential_manager",
            env_configured: false,
            local_store_configured: true,
            can_save: true,
            can_clear: true,
            updated_at: "2026-05-10T00:00:00Z",
            detail: "DeepSeek API key is saved.",
            api_key: "secret",
          },
          { provider: "", label: "Bad", env_name: "BAD", source: "missing" },
        ],
      }),
    ).toEqual({
      schema_version: "desk_ai_settings_status_v1",
      configured_count: 1,
      local_store_supported: true,
      platform: "win32",
      detail: "1 AI provider key configured.",
      checked_at: "2026-05-11T00:00:00Z",
      providers: [
        {
          provider: "deepseek",
          label: "DeepSeek",
          env_name: "DEEPSEEK_API_KEY",
          configured: true,
          source: "windows_credential_manager",
          env_configured: false,
          local_store_configured: true,
          can_save: true,
          can_clear: true,
          updated_at: "2026-05-10T00:00:00Z",
          detail: "DeepSeek API key is saved.",
        },
      ],
    });
    expect(sanitizeDeskAiSettingsStatus({})).toBeNull();
    expect(sanitizeDeskAiSettingsStatus({ schema_version: "desk_ai_settings_status_v1" })).toBeNull();
    expect(
      sanitizeDeskAiSettingsStatus({
        schema_version: "desk_ai_settings_status_v1",
        configured_count: Number.NaN,
        local_store_supported: true,
        platform: "win32",
        detail: "Bad count.",
        providers: [],
      }),
    ).toBeNull();
  });

  it("sanitizes Desk scheduler status without trusting command output", () => {
    expect(
      sanitizeDeskSchedulerStatus({
        schema_version: "desk_scheduler_status_v1",
        available: true,
        installed: true,
        status: " installed ",
        task_label: " jobs-fast dry-run ",
        interval_minutes: 15.8,
        detail: " Checks every 15 minutes. ",
        next_action: " Review Inbox. ",
        checked_at: " 2026-05-10T00:00:00Z ",
        platform: " linux ",
        backend: " linux_systemd_user ",
        profile_id: " frontend-only ",
        display_command: " tgcs schedule print --profile-id frontend-only --interval-minutes 15 --delivery-mode dry-run ",
        last_exit_code: 126,
        can_install: true,
        can_remove: false,
        stdout: "ignored",
        command: "schtasks /Query",
      }),
    ).toEqual({
      schema_version: "desk_scheduler_status_v1",
      available: true,
      installed: true,
      status: "installed",
      task_label: "jobs-fast dry-run",
      interval_minutes: 0,
      detail: "Checks every 15 minutes.",
      next_action: "Review Inbox.",
      checked_at: "2026-05-10T00:00:00Z",
      platform: "linux",
      backend: "linux_systemd_user",
      profile_id: "frontend-only",
      display_command: "tgcs schedule print --profile-id frontend-only --interval-minutes 15 --delivery-mode dry-run",
      last_exit_code: 126,
      can_install: true,
      can_remove: false,
    });

    expect(sanitizeDeskSchedulerStatus({ available: true, installed: false })).toBeNull();
    expect(
      sanitizeDeskSchedulerStatus({
        available: true,
        installed: false,
        status: "not_installed",
        task_label: "jobs-fast dry-run",
        interval_minutes: 15,
        detail: "Background scan is off.",
        next_action: "Install scheduler.",
        checked_at: "2026-05-10T00:00:00Z",
      }),
    ).toBeNull();
  });

  it("sanitizes notification token status only when the local secret contract is explicit", () => {
    expect(
      sanitizeDeskNotificationTokenStatus({
        schema_version: "desk_notification_token_status_v1",
        configured: true,
        source: " local_keyring ",
        updated_at: " 2026-05-10T00:00:00Z ",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: true,
        local_store_backend: " windows_credential_manager ",
        local_store_label: " Windows Credential Manager ",
        can_save: true,
        can_clear: true,
        platform: " win32 ",
        detail: " Telegram bot token is saved locally. ",
        token: "secret",
      }),
    ).toEqual({
      schema_version: "desk_notification_token_status_v1",
      configured: true,
      source: "local_keyring",
      updated_at: "2026-05-10T00:00:00Z",
      env_configured: false,
      local_store_supported: true,
      local_store_configured: true,
      local_store_backend: "windows_credential_manager",
      local_store_label: "Windows Credential Manager",
      can_save: true,
      can_clear: true,
      platform: "win32",
      detail: "Telegram bot token is saved locally.",
    });
    expect(
      sanitizeDeskNotificationTokenStatus({
        configured: false,
        source: "missing",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: false,
        can_save: true,
        can_clear: false,
        platform: "win32",
        detail: "Telegram bot token is not configured.",
      }),
    ).toBeNull();
    expect(
      sanitizeDeskNotificationTokenStatus({
        schema_version: "desk_notification_token_status_v1",
        configured: false,
        source: "missing",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: false,
        can_save: true,
        can_clear: false,
        platform: "",
        detail: "Telegram bot token is not configured.",
      }),
    ).toBeNull();
  });

  it("sanitizes Desk Telegram status without trusting secret backend fields", () => {
    expect(
      sanitizeDeskTelegramStatus({
        schema_version: "desk_telegram_status_v1",
        credentials_ready: true,
        session_ready: false,
        login_state: " code_sent ",
        detail: "Code sent.",
        next_step: "Enter code.",
        config_path: " ~/.config/tgcli/config.toml ",
        session_path: " ~/.config/tgcli/session ",
        api_hash: "secret",
      }),
    ).toEqual({
      schema_version: "desk_telegram_status_v1",
      credentials_ready: true,
      session_ready: false,
      login_state: "code_sent",
      detail: "Code sent.",
      next_step: "Enter code.",
      config_path: "~/.config/tgcli/config.toml",
      session_path: "~/.config/tgcli/session",
    });
    expect(sanitizeDeskTelegramStatus({ credentials_ready: true })).toBeNull();
    expect(
      sanitizeDeskTelegramStatus({
        schema_version: "desk_telegram_status_v1",
        credentials_ready: true,
        session_ready: false,
        login_state: "ready_for_code",
        detail: "",
        next_step: "Send a code.",
        config_path: "~/.config/tgcli/config.toml",
        session_path: "~/.config/tgcli/session",
      }),
    ).toBeNull();
  });
});
