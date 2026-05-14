import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ConsoleHeader } from "./shell";

describe("ConsoleHeader", () => {
  it("uses the header action for a new scan instead of manual state refresh", () => {
    const html = renderToStaticMarkup(
      <ConsoleHeader
        busy={false}
        onNewScan={vi.fn()}
        onOpenUpdates={vi.fn()}
        updateAvailableCount={0}
      />,
    );

    expect(html).toContain("New scan");
    expect(html).toContain("Run fresh AI review");
    expect(html).not.toContain("Refresh");
    expect(html).not.toContain("Refresh state");
  });
});
