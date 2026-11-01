const CITATION_PATTERN = /^(KB[12])\/(.*?)(?:\s+p\.(\d+))?(?:\s+c\.(\d+))?$/;

export function parseCitation(label) {
  const raw = String(label || "").trim();
  const match = CITATION_PATTERN.exec(raw);
  if (!match) {
    return { label: raw, knowledgeBase: null, document: raw, page: null, chunk: null };
  }
  return {
    label: raw,
    knowledgeBase: match[1],
    document: match[2],
    page: match[3] ? Number(match[3]) : null,
    chunk: match[4] ? Number(match[4]) : null,
  };
}

function pushAll(target, values) {
  for (const value of values || []) {
    if (value) target.add(String(value));
  }
}

/** Collect every citation the backend returned for one analysis. */
export function collectCitations(result) {
  const seen = new Set();
  const report = result?.report || {};

  pushAll(seen, report.citations);
  for (const section of [
    report.policy_coverage_gaps,
    report.implementation_gaps,
    report.institutional_gaps,
    report.evidence_gaps,
  ]) {
    for (const gap of section || []) {
      pushAll(seen, gap.citations);
    }
  }

  for (const findings of [result?.policy_findings, result?.needs_findings]) {
    pushAll(seen, findings?.citations);
  }

  for (const message of result?.communication || []) {
    pushAll(seen, message.citations);
    for (const evidence of message.evidence || []) {
      pushAll(seen, [evidence.citation]);
    }
  }

  return Array.from(seen).map(parseCitation);
}
