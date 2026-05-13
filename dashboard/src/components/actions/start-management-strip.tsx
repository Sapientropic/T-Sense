import { Bell, CircleDashed, KeyRound, UserRoundCog, Wrench } from "lucide-react";
import type { ReactNode } from "react";

import type { DeskSchedulerStatus } from "../../domain/types";
import type { JourneyStep } from "./journey-model";
import type { SettingsShortcutTarget } from "./types";

type StartManagementControl = {
  key: string;
  label: string;
  detail: string;
  icon: ReactNode;
  disabled?: boolean;
  onClick: () => void;
};

export function StartManagementStrip({
  anyBusy,
  automationStep,
  onOpenProfiles,
  onOpenRuns,
  onOpenSettings,
  onRun,
  scheduler,
  setupOpen,
  onToggleSetup,
}: {
  anyBusy: boolean;
  automationStep?: JourneyStep;
  onOpenProfiles?: () => void;
  onOpenRuns?: () => void;
  onOpenSettings?: (target?: SettingsShortcutTarget) => void;
  onRun: (actionId: string) => Promise<void>;
  scheduler?: DeskSchedulerStatus | null;
  setupOpen: boolean;
  onToggleSetup: () => void;
}) {
  const automationButton =
    automationStep?.buttons.find((button) => button.actionId === "schedule_install_dry_run" || button.actionId === "schedule_remove_dry_run") ??
    automationStep?.buttons.find((button) => button.actionId === "schedule_preview");
  const controls: StartManagementControl[] = [
    ...(automationButton
      ? [
          {
            key: "automation",
            label: scheduler?.installed ? "Auto scan on" : "Automation",
            detail: scheduler?.installed ? "Every 15 min" : "Set schedule",
            icon: <Bell size={15} />,
            disabled: anyBusy,
            onClick: () => void onRun(automationButton.actionId),
          } satisfies StartManagementControl,
        ]
      : []),
    {
      key: "setup",
      label: "Setup",
      detail: setupOpen ? "Hide setup" : "Edit / login",
      icon: <Wrench size={15} />,
      onClick: onToggleSetup,
    },
    {
      key: "ai",
      label: "AI API",
      detail: "LLM / OCR keys",
      icon: <KeyRound size={15} />,
      disabled: !onOpenSettings,
      onClick: () => onOpenSettings?.("ai"),
    },
    {
      key: "profiles",
      label: "Profiles",
      detail: "Create / edit",
      icon: <UserRoundCog size={15} />,
      disabled: !onOpenProfiles,
      onClick: () => onOpenProfiles?.(),
    },
    {
      key: "sources",
      label: "Sources",
      detail: "Channels",
      icon: <Wrench size={15} />,
      disabled: !onOpenSettings,
      onClick: () => onOpenSettings?.("sources"),
    },
    {
      key: "runs",
      label: "Runs",
      detail: "Open evidence",
      icon: <CircleDashed size={15} />,
      disabled: !onOpenRuns,
      onClick: () => onOpenRuns?.(),
    },
  ];
  return (
    <nav className="start-management-strip" aria-label="Desk management shortcuts">
      {controls.map((control) => (
        <button data-control-key={control.key} disabled={control.disabled} key={control.key} onClick={control.onClick} type="button">
          {control.icon}
          <span>{control.label}</span>
          <small>{control.detail}</small>
        </button>
      ))}
    </nav>
  );
}
