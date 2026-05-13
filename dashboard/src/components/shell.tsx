import type { ReactNode } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";

import signalIcon from "../assets/tgcs-signal-icon.png";
import type { Tab } from "../domain/types";

export function ConsoleHeader({
  busy,
  onOpenUpdates,
  onRefresh,
}: {
  busy: boolean;
  onOpenUpdates: () => void;
  onRefresh: () => void;
}) {
  return (
    <header className="console-header">
      <div className="brand-station">
        <button
          className="pixel-mark"
          aria-label="Open updates"
          onClick={onOpenUpdates}
          title="Open updates"
          type="button"
        >
          <img src={signalIcon} alt="" />
        </button>
        <div className="brand-copy">
          <p className="eyebrow">T-Sense</p>
          <h1>Signal Desk</h1>
          <div className="header-readout" aria-label="Local dashboard boundary">
            <span>Local app</span>
            <span>Data stays local</span>
            <span>Raw text hidden</span>
          </div>
        </div>
      </div>
      <button className="refresh-button" onClick={onRefresh} disabled={busy} title="Refresh state" type="button">
        <RefreshCw size={18} className={busy ? "spin" : ""} />
        <span>Refresh</span>
      </button>
    </header>
  );
}

export function NavigationRail({
  tabs,
  activeTab,
  tabCounts,
  setActiveTab,
}: {
  tabs: Array<{ tab: Tab; icon: ReactNode; label: string }>;
  activeTab: Tab;
  tabCounts: Record<Tab, number>;
  setActiveTab: (tab: Tab) => void;
}) {
  return (
    <aside className="nav-rail" aria-label="Dashboard navigation">
      <nav className="tabs" aria-label="Dashboard tabs">
        {tabs.map((tab) => (
          <TabButton key={tab.tab} {...tab} active={activeTab} count={tabCounts[tab.tab]} setActive={setActiveTab} />
        ))}
      </nav>
      <div className="rail-note">
        <ShieldCheck size={16} />
        <span>Secrets stay local</span>
      </div>
    </aside>
  );
}

function TabButton({
  tab,
  active,
  count,
  setActive,
  icon,
  label,
}: {
  tab: Tab;
  active: Tab;
  count: number;
  setActive: (tab: Tab) => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      className={active === tab ? "tab active" : "tab"}
      aria-current={active === tab ? "page" : undefined}
      onClick={() => setActive(tab)}
      type="button"
    >
      <span className="tab-icon">{icon}</span>
      <span className="tab-label">{label}</span>
      <span className="tab-count">{count}</span>
    </button>
  );
}

export function WorkbenchHeader({
  meta,
}: {
  meta: {
    title: string;
    detail: string;
    value: string;
    tone: "amber" | "teal" | "rust" | "blue";
  };
}) {
  return (
    <header className="board-header" title={meta.detail}>
      <div>
        <h2>{meta.title}</h2>
      </div>
      <strong className={`board-token ${meta.tone}`}>{meta.value}</strong>
    </header>
  );
}
