export function parseDiff(diffText: string) {
  const lines = diffText.split("\n");
  const added: string[] = [];
  const removed: string[] = [];
  for (const line of lines) {
    if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) {
      continue;
    }
    if (line.startsWith("+")) {
      const item = cleanDiffLine(line.substring(1));
      if (item) {
        added.push(item);
      }
    } else if (line.startsWith("-")) {
      const item = cleanDiffLine(line.substring(1));
      if (item) {
        removed.push(item);
      }
    }
  }
  return { added, removed };
}

function cleanDiffLine(line: string) {
  const cleaned = line
    .replace(/^\s*[-*]\s+/, "")
    .replace(/^\s*\+\s*/, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .trim();
  if (!cleaned || cleaned === "## Follow-up Preferences") {
    return "";
  }
  if (cleaned.startsWith("Desk feedback tuning: prefer matches like")) {
    return "Extract broad matching preferences from your confirmed Review choices.";
  }
  if (cleaned.startsWith("Desk feedback tuning: Analyze")) {
    return "Turn Keep / Skip / Wrong Match decisions into reusable matching rules.";
  }
  return cleaned;
}
