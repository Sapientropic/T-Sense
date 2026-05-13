import { formatScanWindow, titleCaseLabel } from "../../domain/format";
import type { Profile } from "../../domain/types";

export function profileScanWindowLabel(profile: Profile) {
  const formatted = formatScanWindow(profile.scan_window_hours).toLowerCase();
  return formatted === "window n/a" ? "Scan history" : formatted.replace(" scan", " history");
}

export function profileItemLimitLabel(profile: Profile) {
  if (typeof profile.semantic_max_messages !== "number") {
    return "Item limit";
  }
  return `${profile.semantic_max_messages} messages`;
}

export function profileTopicLabel(profile: Profile) {
  return profile.source_topics?.[0] ? titleCaseLabel(profile.source_topics[0]) : "All topics";
}

export function profileNotificationLabel(profile: Profile) {
  if (typeof profile.delivery_target_count !== "number") {
    return "Notifications";
  }
  return profile.delivery_target_count === 1 ? "1 notification" : `${profile.delivery_target_count} notifications`;
}
