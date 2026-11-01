const STORAGE_KEY = "agrobridge.gap.threads.v1";
const MAX_THREADS = 20;

function newId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createThread() {
  const now = new Date().toISOString();
  return { id: newId(), title: "New analysis", createdAt: now, updatedAt: now, messages: [] };
}

export function loadThreads() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((thread) => thread && thread.id && Array.isArray(thread.messages));
  } catch {
    return [];
  }
}

export function saveThreads(threads) {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify((threads || []).slice(0, MAX_THREADS)),
    );
  } catch {
    // Storage may be full or disabled; the session still works in memory.
  }
}

export function threadTitle(query) {
  const clean = String(query || "").replace(/\s+/g, " ").trim();
  if (!clean) return "New analysis";
  return clean.length > 64 ? `${clean.slice(0, 61)}…` : clean;
}

export function relativeTime(iso) {
  const date = new Date(iso);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (Number.isNaN(seconds)) return "";
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString();
}
