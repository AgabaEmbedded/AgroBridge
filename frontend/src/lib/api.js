const RAW_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

const GAP_TOKEN =
  import.meta.env.VITE_POLICY_API_TOKEN || import.meta.env.VITE_GAP_API_TOKEN || "";

export class ApiError extends Error {
  constructor(message, status = 0, detail = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseResponse(response) {
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const detail =
      (body && (body.detail || body.message)) ||
      text.slice(0, 300) ||
      `HTTP ${response.status}`;
    throw new ApiError(String(detail), response.status, String(detail));
  }
  return body;
}

export async function fetchHealth({ signal } = {}) {
  const response = await fetch(`${API_BASE}/health`, { signal });
  return parseResponse(response);
}

/**
 * Run the Policy Analyzer workflow. The backend is intentionally stateless: every call is a
 * complete analysis, so calling this twice with follow-ups starts two independent runs.
 */
export async function runGapAnalysis({ query, maxRounds, signal }) {
  const headers = { "Content-Type": "application/json" };
  if (GAP_TOKEN) headers["X-Policy-Token"] = GAP_TOKEN;

  const payload = { query };
  if (Number.isInteger(maxRounds)) payload.max_rounds = maxRounds;

  let response;
  try {
    response = await fetch(`${API_BASE}/api/policy-analyzer`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(
      `Cannot reach the AgroBridge backend at ${API_BASE}. Is it running?`,
      0,
      error.message,
    );
  }
  return parseResponse(response);
}
