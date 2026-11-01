export const GAP_SECTIONS = [
  {
    key: "policy_coverage_gaps",
    title: "Policy coverage gaps",
    description: "Practical needs that existing commitments do not adequately address.",
  },
  {
    key: "implementation_gaps",
    title: "Implementation gaps",
    description: "Commitments where the available evidence shows incomplete delivery.",
  },
  {
    key: "institutional_gaps",
    title: "Institutional gaps",
    description: "Unclear, overlapping or missing responsibilities and coordination.",
  },
  {
    key: "evidence_gaps",
    title: "Evidence gaps",
    description: "Areas where the supplied documents cannot establish implementation.",
  },
];

export const STATUS_META = {
  confirmed_shortfall: {
    label: "Confirmed shortfall",
    variant: "destructive",
    description: "Evidence directly shows the commitment was not met.",
  },
  potential_gap: {
    label: "Potential gap",
    variant: "warning",
    description: "Evidence suggests a gap but is not conclusive.",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    variant: "muted",
    description: "The documents do not establish whether this was implemented.",
  },
};

export function statusMeta(status) {
  return (
    STATUS_META[status] || {
      label: status ? String(status).replaceAll("_", " ") : "Unclassified",
      variant: "outline",
      description: "The backend did not label an evidence status.",
    }
  );
}

export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function timingEntries(timings) {
  const labels = {
    ga1_ms: "GA1 policy analysis",
    ga2_ms: "GA2 needs analysis",
    communication_ms: "Agent communication",
    synthesis_ms: "Synthesis",
  };
  return Object.entries(timings || {})
    .map(([key, value]) => ({
      key,
      label: labels[key] || key.replaceAll("_", " "),
      value,
    }))
    .filter((item) => Number.isFinite(item.value));
}
