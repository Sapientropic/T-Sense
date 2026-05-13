import type { DeliveryTarget } from "../types";
import { isRecord, optionalString, sanitizeObjectArray } from "./shared";
import { assignOptionalStrings, requiredString, stringOrDefault } from "./dashboard-common";

export function sanitizeDeliveryTargets(value: unknown): DeliveryTarget[] {
  return sanitizeObjectArray(value, "delivery_targets").flatMap((record, index) => {
    if (record.schema_version !== "delivery_target_v1") {
      return [];
    }
    const targetId = requiredString(index, "target_id", record.target_id, "delivery_targets");
    const type = requiredString(index, "type", record.type, "delivery_targets");
    if (!targetId || !type) {
      return [];
    }
    const target: DeliveryTarget = {
      schema_version: "delivery_target_v1",
      target_id: targetId,
      type,
      enabled: typeof record.enabled === "boolean" ? record.enabled : false,
      config: sanitizeDeliveryTargetConfig(record.config),
      updated_at: stringOrDefault(record.updated_at, ""),
    };
    assignOptionalStrings(target, record, ["display_name", "status_label", "detail"]);
    return [target];
  });
}

function sanitizeDeliveryTargetConfig(value: unknown): Record<string, unknown> {
  const record = isRecord(value) ? value : {};
  const chatId = optionalString(record.chat_id);
  return chatId ? { chat_id: chatId } : {};
}
