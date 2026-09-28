"use client";

// Indicator / overlay / profile toggles. Port of ../ui/sidebar.py.
import { maColors } from "@/lib/theme";
import type { IndicatorConfig, MaConfig, OverlayConfig, ProfileMode } from "@/lib/types";

interface Props {
  indicators: IndicatorConfig;
  onIndicatorsChange: (i: IndicatorConfig) => void;
  overlays: OverlayConfig;
  onOverlaysChange: (o: OverlayConfig) => void;
  profileMode: ProfileMode;
  onProfileModeChange: (m: ProfileMode) => void;
  marketProfileEnabled: boolean;
  onMarketProfileChange: (b: boolean) => void;
  atrValue: number | null;
}

const OVERLAY_ITEMS: { label: string; key: keyof OverlayConfig }[] = [
  { label: "Prev day VA", key: "prevDay" },
  { label: "Prev week VA", key: "prevWeek" },
  { label: "Prev month VA", key: "prevMonth" },
  { label: "Session open", key: "sessionOpen" },
  { label: "Overnight range", key: "overnight" },
  { label: "Naked POC", key: "nakedPoc" },
];

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="group-box" style={{ marginBottom: 10 }}>
      <div className="group-title">{title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export default function Sidebar({
  indicators, onIndicatorsChange, overlays, onOverlaysChange,
  profileMode, onProfileModeChange, marketProfileEnabled, onMarketProfileChange, atrValue,
}: Props) {
  const addMa = () => {
    const id = `ma${Date.now()}`;
    const ma: MaConfig = {
      id, kind: "EMA", period: 20,
      color: maColors[indicators.mas.length % maColors.length],
      width: 1.5, enabled: true,
    };
    onIndicatorsChange({ ...indicators, mas: [...indicators.mas, ma] });
  };
  const updateMa = (id: string, patch: Partial<MaConfig>) => {
    onIndicatorsChange({ ...indicators, mas: indicators.mas.map((m) => (m.id === id ? { ...m, ...patch } : m)) });
  };
  const removeMa = (id: string) => {
    onIndicatorsChange({ ...indicators, mas: indicators.mas.filter((m) => m.id !== id) });
  };

  return (
    <div style={{ width: 260, overflowY: "auto", padding: 8, borderRight: "1px solid var(--border)" }}>
      <Group title="Moving Averages">
        {indicators.mas.map((ma) => (
          <div key={ma.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <input type="checkbox" checked={ma.enabled} onChange={(e) => updateMa(ma.id, { enabled: e.target.checked })} />
            <select value={ma.kind} onChange={(e) => updateMa(ma.id, { kind: e.target.value as "EMA" | "SMA" })} style={{ width: 56 }}>
              <option value="EMA">EMA</option>
              <option value="SMA">SMA</option>
            </select>
            <input
              type="number" min={1} max={500} value={ma.period}
              onChange={(e) => updateMa(ma.id, { period: Number(e.target.value) || 1 })}
              style={{ width: 48 }}
            />
            <input
              type="color" value={ma.color}
              onChange={(e) => updateMa(ma.id, { color: e.target.value })}
              style={{ width: 24, height: 24, padding: 0 }}
            />
            <button onClick={() => removeMa(ma.id)} style={{ padding: "2px 6px" }}>✕</button>
          </div>
        ))}
        <button onClick={addMa}>+ Add MA</button>
      </Group>

      <Group title="Momentum">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Check label="RSI" checked={indicators.rsi.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, rsi: { ...indicators.rsi, enabled: v } })} />
          <input
            type="number" min={2} max={100} value={indicators.rsi.period}
            onChange={(e) => onIndicatorsChange({ ...indicators, rsi: { ...indicators.rsi, period: Number(e.target.value) || 14 } })}
            style={{ width: 48 }}
          />
        </div>
        <Check label="MACD (12,26,9)" checked={indicators.macd.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, macd: { enabled: v } })} />
      </Group>

      <Group title="Volatility">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Check label="Bollinger" checked={indicators.bollinger.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, bollinger: { ...indicators.bollinger, enabled: v } })} />
          <input
            type="number" min={2} max={100} value={indicators.bollinger.period}
            onChange={(e) => onIndicatorsChange({ ...indicators, bollinger: { ...indicators.bollinger, period: Number(e.target.value) || 20 } })}
            style={{ width: 44 }}
          />
          <input
            type="number" min={0.5} max={5} step={0.5} value={indicators.bollinger.mult}
            onChange={(e) => onIndicatorsChange({ ...indicators, bollinger: { ...indicators.bollinger, mult: Number(e.target.value) || 2 } })}
            style={{ width: 44 }}
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Check label="ATR label" checked={indicators.atr.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, atr: { enabled: v } })} />
          {indicators.atr.enabled && atrValue != null && (
            <span style={{ color: "var(--text-muted)" }}>{atrValue.toFixed(3)}</span>
          )}
        </div>
      </Group>

      <Group title="Volume">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Check label="VWAP (session)" checked={indicators.vwap.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, vwap: { ...indicators.vwap, enabled: v } })} />
        </div>
        <Check label="VWAP std-dev bands" checked={indicators.vwap.bands} onChange={(v) => onIndicatorsChange({ ...indicators, vwap: { ...indicators.vwap, bands: v } })} />
        <Check label="Volume MA (20)" checked={indicators.volumeMa.enabled} onChange={(v) => onIndicatorsChange({ ...indicators, volumeMa: { enabled: v } })} />
      </Group>

      <Group title="Profiles">
        <div>Volume Profile</div>
        <select value={profileMode} onChange={(e) => onProfileModeChange(e.target.value as ProfileMode)}>
          <option value="off">Off</option>
          <option value="visible">Visible range</option>
          <option value="sessions">Last 3 sessions</option>
        </select>
        <Check label="Market Profile (TPO, daily)" checked={marketProfileEnabled} onChange={onMarketProfileChange} />
      </Group>

      <Group title="AMT Overlays">
        {OVERLAY_ITEMS.map((item) => (
          <Check
            key={item.key}
            label={item.label}
            checked={overlays[item.key]}
            onChange={(v) => onOverlaysChange({ ...overlays, [item.key]: v })}
          />
        ))}
      </Group>

      <Group title="Session / Time">
        <Check label="Session separators" checked={overlays.sessions} onChange={(v) => onOverlaysChange({ ...overlays, sessions: v })} />
      </Group>
    </div>
  );
}
