export function formatDate(value?: string) {
  if (!value) {
    return "unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function formatScanWindow(hours?: number) {
  return hours && hours > 0 ? `${hours}h scan` : "Default scan";
}

export function formatSemanticCap(maxMessages?: number) {
  return maxMessages && maxMessages > 0 ? `${maxMessages} semantic` : "Default semantic";
}

export function formatTargetCount(count?: number) {
  const value = count ?? 0;
  return `${value} target${value === 1 ? "" : "s"}`;
}

export function formatPercent(value: number) {
  if (!Number.isFinite(value)) {
    return "0%";
  }
  return `${Math.round(value * 100)}%`;
}

const tokenOverrides: Record<string, string> = {
  ai: "AI",
  api: "API",
  css: "CSS",
  eu: "EU",
  golang: "Go",
  html: "HTML",
  hr: "HR",
  it: "IT",
  js: "JS",
  javascript: "JavaScript",
  nodejs: "Node.js",
  pm: "PM",
  qa: "QA",
  react: "React",
  remoute: "Remote",
  rus: "RU",
  ts: "TS",
  typescript: "TypeScript",
  ui: "UI",
  us: "US",
  ux: "UX",
  webdevelopment: "Web Development",
};

const diagnosticLabels: Record<string, string> = {
  all_filtered_out: "All filtered out",
  bypassed_scan_input: "Saved scan input",
  channel_failures: "Source access failed",
  llm_unavailable: "LLM unavailable",
  missing_scan_metadata: "Scan metadata missing",
  no_messages_fetched: "No messages fetched",
  ocr_disabled_media_present: "OCR media skipped",
  scan_failed: "Scan failed",
  scan_incomplete: "Scan incomplete",
};

export function titleCaseLabel(value: string) {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => tokenOverrides[part.toLowerCase()] || part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function compactReportName(name: string) {
  return name
    .replace(/\s+(Signal Report|Signal Brief|Scan Report|Report|Brief)$/i, "")
    .trim() || name;
}

export function profileDisplayName(profileId: string) {
  return profileId
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Profile";
}

export function channelDisplayName(channel: string) {
  return titleCaseLabel(String(channel || "").replace(/^@+/, "")) || "Unknown Source";
}

export function sourceRefLabel(ref: { channel?: string }) {
  return channelDisplayName(String(ref.channel || ""));
}

export function decisionStatusLabel(status?: string | null) {
  const safeStatus = String(status || "");
  const normalized = safeStatus.toLowerCase();
  if (normalized === "new") {
    return "New";
  }
  if (normalized === "changed") {
    return "Changed";
  }
  if (normalized === "seen") {
    return "Seen";
  }
  if (normalized === "recurring") {
    return "Recurring";
  }
  return titleCaseLabel(safeStatus || "Unknown");
}

export function diagnosticLabel(code: string) {
  return diagnosticLabels[code] || titleCaseLabel(code);
}
