import type { DeskTelegramStatus } from "../../domain/types";

export type SettingsShortcutTarget = "sources" | "ai" | "notifications" | "learning";

export type TelegramControls = {
  status: DeskTelegramStatus | null;
  busy: string;
  error: string;
  saveCredentials: (apiId: string, apiHash: string) => Promise<DeskTelegramStatus>;
  sendCode: (phone: string) => Promise<DeskTelegramStatus>;
  verifyCode: (code: string, password?: string) => Promise<DeskTelegramStatus>;
  refresh: () => Promise<DeskTelegramStatus>;
  cancelLogin: () => Promise<DeskTelegramStatus>;
};
