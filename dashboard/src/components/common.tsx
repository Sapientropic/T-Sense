import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Check, Copy } from "lucide-react";

/** Shared panel title row; count is optional because some rail panels are status-only. */
export function PanelHeader({ icon, title, count }: { icon: ReactNode; title: string; count?: number }) {
  return (
    <header className="panel-header">
      <span className="panel-title">
        {icon}
        {title}
      </span>
      {typeof count === "number" && <span className="count-badge">{count}</span>}
    </header>
  );
}

/** Compact list/table empty state that keeps the warning icon consistent across views. */
export function InlineEmpty({ title }: { title: string }) {
  return (
    <div className="inline-empty">
      <AlertTriangle size={16} />
      <span>{title}</span>
    </div>
  );
}

export function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function EmptyStateShell({
  icon,
  title,
  detail,
  readout,
  children,
}: {
  icon: ReactNode;
  title: string;
  detail?: string;
  readout: Array<{ label: string; value: string }>;
  children?: ReactNode;
}) {
  return (
    <section className="empty-state">
      <div className="empty-radar" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="empty-icon">{icon}</div>
      <div className="empty-copy">
        <h3>{title}</h3>
        {detail && <p>{detail}</p>}
      </div>
      {children}
      <div className="empty-readout" aria-label="Empty state readout">
        {readout.map((item) => (
          <StatusLine label={item.label} value={item.value} key={item.label} />
        ))}
      </div>
    </section>
  );
}

type CopyStatus = "idle" | "copied" | "failed";

function copyWithLegacyFallback(command: string) {
  if (typeof document === "undefined") {
    return false;
  }
  const textarea = document.createElement("textarea");
  textarea.value = command;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

export function CopyableCommand({
  command,
  label,
  compact = false,
  iconOnly = false,
}: {
  command: string;
  label: string;
  compact?: boolean;
  iconOnly?: boolean;
}) {
  const [status, setStatus] = useState<CopyStatus>("idle");
  const resetTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
    };
  }, []);

  function scheduleStatus(nextStatus: CopyStatus) {
    setStatus(nextStatus);
    if (resetTimer.current !== null) {
      window.clearTimeout(resetTimer.current);
    }
    resetTimer.current = window.setTimeout(() => setStatus("idle"), 1200);
  }

  async function copyCommand() {
    let copied = false;
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(command);
        copied = true;
      }
    } catch {
      copied = false;
    }
    if (!copied) {
      copied = copyWithLegacyFallback(command);
    }
    scheduleStatus(copied ? "copied" : "failed");
  }
  const copied = status === "copied";
  const failed = status === "failed";
  const title = copied ? "Copied" : failed ? "Copy failed" : compact ? command : "Copy command";
  const ariaLabel = failed ? `Copy ${label} command failed` : `Copy ${label} command`;
  const icon = failed ? <AlertTriangle size={14} /> : copied ? <Check size={14} /> : <Copy size={14} />;
  const compactClassName = ["copy-command-button", iconOnly ? "icon-only" : "", failed ? "copy-failed" : ""]
    .filter(Boolean)
    .join(" ");
  if (compact) {
    return (
      <button
        className={compactClassName}
        aria-label={ariaLabel}
        onClick={() => void copyCommand()}
        title={title}
        type="button"
      >
        {icon}
        {!iconOnly && <span>{copied ? "Copied" : failed ? "Copy failed" : "Copy command"}</span>}
      </button>
    );
  }
  return (
    <div className="copyable-command">
      <code>{command}</code>
      <button
        className={failed ? "copy-failed" : undefined}
        aria-label={ariaLabel}
        onClick={() => void copyCommand()}
        title={title}
        type="button"
      >
        {icon}
      </button>
    </div>
  );
}
