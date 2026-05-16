export type SettingsTask = "sources" | "ai" | "notifications" | "learning" | "updates";

export function SettingsTaskSwitch({
  activeTask,
  sourceCount,
  sourceDetail,
  aiCount,
  notificationCount,
  feedbackCount,
  updateCount,
  onSelect,
}: {
  activeTask: SettingsTask;
  sourceCount: number;
  sourceDetail?: string;
  aiCount: number;
  notificationCount: number;
  feedbackCount: number;
  updateCount: number;
  onSelect: (task: SettingsTask) => void;
}) {
  const tasks: Array<{ id: SettingsTask; label: string; count: number; detail: string }> = [
    { id: "sources", label: "Sources", count: sourceCount, detail: sourceDetail || "Tracked channels" },
    { id: "ai", label: "AI API", count: aiCount, detail: "Matching and image reading" },
    { id: "notifications", label: "Alerts", count: notificationCount, detail: "Where alerts go" },
    {
      id: "learning",
      label: "Learning",
      count: feedbackCount,
      detail: feedbackCount > 0 ? "Use Review choices" : "Review cards to teach preferences",
    },
    { id: "updates", label: "Updates", count: updateCount, detail: updateCount > 0 ? "New app version" : "App version" },
  ];
  return (
    <div className="settings-task-switch" aria-label="Settings task switcher">
      {tasks.map((task) => (
        <button
          aria-pressed={activeTask === task.id}
          data-empty={task.count === 0 ? "true" : "false"}
          key={task.id}
          onClick={() => onSelect(task.id)}
          type="button"
        >
          <span>{task.label}</span>
          <strong>{task.count}</strong>
          <small>{task.detail}</small>
        </button>
      ))}
    </div>
  );
}
