// Browser localStorage persistence, replacing ../db/database.py's SQLite
// tables with the same logical shape: settings, drawings per ticker+
// timeframe, journal notes per ticker, and the paper-trading engine state.
// All reads/writes are guarded for SSR since Next.js renders this module's
// callers on the server too.
import type { Drawing, JournalNote } from "./types";
import type { PaperState } from "./paperEngine";

const PREFIX = "amt:";

function isBrowser() {
  return typeof window !== "undefined";
}

function read<T>(key: string, fallback: T): T {
  if (!isBrowser()) return fallback;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write<T>(key: string, value: T): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // storage full or unavailable — nothing sensible to do for a personal tool
  }
}

export interface Settings {
  ticker: string;
  timeframe: string;
  sidebarState?: unknown;
}

export function getSettings(defaults: Settings): Settings {
  return read("settings", defaults);
}

export function setSettings(settings: Settings): void {
  write("settings", settings);
}

export function loadDrawings(ticker: string, timeframe: string): Drawing[] {
  return read(`drawings:${ticker}:${timeframe}`, [] as Drawing[]);
}

export function saveDrawings(ticker: string, timeframe: string, drawings: Drawing[]): void {
  write(`drawings:${ticker}:${timeframe}`, drawings);
}

export function loadJournal(ticker: string): JournalNote[] {
  return read(`journal:${ticker}`, [] as JournalNote[]);
}

export function saveJournal(ticker: string, notes: JournalNote[]): void {
  write(`journal:${ticker}`, notes);
}

export function loadPaperState(fallback: PaperState): PaperState {
  return read("paper", fallback);
}

export function savePaperState(state: PaperState): void {
  write("paper", state);
}
