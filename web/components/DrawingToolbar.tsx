"use client";

import type { DrawingKind } from "@/lib/types";

const TOOLS: { label: string; kind: DrawingKind; key: string }[] = [
  { label: "Horizontal line", kind: "hline", key: "H" },
  { label: "Vertical line", kind: "vline", key: "V" },
  { label: "Trend line", kind: "trend", key: "T" },
  { label: "Rectangle", kind: "rect", key: "B" },
  { label: "Text label", kind: "text", key: "L" },
];

interface Props {
  activeTool: DrawingKind | null;
  onSelectTool: (k: DrawingKind) => void;
  onDeleteSelected: () => void;
  onClearAll: () => void;
  hasSelection: boolean;
}

export default function DrawingToolbar({ activeTool, onSelectTool, onDeleteSelected, onClearAll, hasSelection }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: 4, borderRight: "1px solid var(--border)" }}>
      {TOOLS.map((t) => (
        <button
          key={t.kind}
          title={`${t.label} (${t.key})`}
          onClick={() => onSelectTool(t.kind)}
          style={{
            background: activeTool === t.kind ? "var(--accent)" : undefined,
            width: 34, height: 30, fontSize: 10,
          }}
        >
          {t.key}
        </button>
      ))}
      <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
      <button title="Delete selected (Del)" onClick={onDeleteSelected} disabled={!hasSelection} style={{ width: 34, height: 30, fontSize: 10 }}>
        ✕
      </button>
      <button title="Clear all drawings" onClick={onClearAll} style={{ width: 34, height: 30, fontSize: 9 }}>
        clr
      </button>
    </div>
  );
}
