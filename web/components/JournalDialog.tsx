"use client";

// Journal note dialog: add a note (right-click on the chart) or view/delete
// an existing one (click a flag). Port of ../ui/journal.py's JournalDialog.
import { useState } from "react";
import type { JournalNote, Trade } from "@/lib/types";

interface AddProps {
  mode: "add";
  ts: number;
  price: number | null;
  trades: Trade[];
  onSave: (text: string, tradeId: number | null) => void;
  onClose: () => void;
}

interface ViewProps {
  mode: "view";
  note: JournalNote;
  onDelete: () => void;
  onClose: () => void;
}

type Props = AddProps | ViewProps;

function fmt(ts: number) {
  return new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 16);
}

export default function JournalDialog(props: Props) {
  const [text, setText] = useState("");
  const [tradeId, setTradeId] = useState<number | null>(null);

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
      onClick={props.onClose}
    >
      <div className="group-box" style={{ background: "var(--panel)", width: 340, padding: 16 }} onClick={(e) => e.stopPropagation()}>
        {props.mode === "add" ? (
          <>
            <div style={{ marginBottom: 8 }}>{fmt(props.ts)} {props.price != null && `@ ${props.price.toFixed(2)}`}</div>
            <textarea
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Write your note…"
              rows={4}
              style={{ width: "100%", resize: "vertical", marginBottom: 8 }}
            />
            {props.trades.length > 0 && (
              <>
                <div style={{ marginBottom: 4, color: "var(--text-muted)" }}>Link to trade (optional):</div>
                <select
                  value={tradeId ?? ""}
                  onChange={(e) => setTradeId(e.target.value ? Number(e.target.value) : null)}
                  style={{ width: "100%", marginBottom: 8 }}
                >
                  <option value="">— none —</option>
                  {props.trades.map((t) => (
                    <option key={t.id} value={t.id}>#{t.id} {t.side} {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}</option>
                  ))}
                </select>
              </>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
              <button onClick={props.onClose}>Cancel</button>
              <button
                onClick={() => {
                  if (text.trim()) props.onSave(text.trim(), tradeId);
                  props.onClose();
                }}
              >
                OK
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ marginBottom: 8, color: "var(--text-muted)" }}>
              {fmt(props.note.ts)} {props.note.price != null && `@ ${props.note.price.toFixed(2)}`}
            </div>
            <div style={{ marginBottom: 12, whiteSpace: "pre-wrap" }}>{props.note.note}</div>
            {props.note.tradeId != null && (
              <div style={{ marginBottom: 12, color: "var(--text-muted)" }}>linked to trade #{props.note.tradeId}</div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
              <button onClick={props.onClose}>Close</button>
              <button onClick={() => { props.onDelete(); props.onClose(); }}>Delete note</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
