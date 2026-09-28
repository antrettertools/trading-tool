// Ported verbatim from ../config.example.json's "theme" block + the desktop
// app's DARK_QSS (main.py) so the web app matches the PySide6 app's look.
export const theme = {
  background: "#131722",
  panel: "#1e222d",
  border: "#2a2e39",
  borderLight: "#363a45",
  grid: "#1e222d",
  text: "#d1d4dc",
  textMuted: "#787b86",
  candleUp: "#26a69a",
  candleDown: "#ef5350",
  accent: "#2962ff",
  poc: "#ffeb3b",
  vah: "#26a69a",
  val: "#ef5350",
  journalFlag: "#ffca28",
} as const;

export const maColors = ["#42a5f5", "#ffb74d", "#ab47bc", "#26c6da", "#ec407a"];
