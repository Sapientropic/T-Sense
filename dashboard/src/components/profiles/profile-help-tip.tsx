import { CircleHelp } from "lucide-react";

export function ProfileHelpTip({ text }: { text: string }) {
  return (
    <span className="profile-help-tip" aria-label={text} tabIndex={0}>
      <CircleHelp size={13} aria-hidden="true" />
      <span role="tooltip">{text}</span>
    </span>
  );
}
