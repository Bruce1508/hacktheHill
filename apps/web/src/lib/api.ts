const API_HEADERS = { "X-Demo-User": "demo-agent" };

export type RunOut = {
  run_id: string;
  dataset_profile: string;
  dataset_seed: number;
  started_at: string;
  finished_at: string | null;
};

export async function fetchLatestRun(): Promise<RunOut> {
  const res = await fetch(`${API_URL}/runs/latest`, {
    cache: "no-store",
    headers: API_HEADERS,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch latest run: ${res.status}`);
  }
  return res.json();
}

export type CohortOut = {
  id: string;
  run_id: string;
  status: string;
  kind: string;
  hypothesis: string | null;
  confidence: number | null;
  member_count: number;
};

export type CohortEvidenceOut = {
  cohort_id: string;
  score_components: Record<string, number>;
  hypothesis: string | null;
  hypothesis_citations: { complaint_ids: string[]; event_ids: string[]; anomaly_ids: string[] } | null;
  linked_event_ids: string[];
  linked_anomaly_ids: string[];
  sample_complaint_ids: string[];
};

export async function listCohorts(runId: string): Promise<{ cohorts: CohortOut[] }> {
  const res = await fetch(`${API_URL}/cohorts?run_id=${encodeURIComponent(runId)}`, {
    cache: "no-store",
    headers: API_HEADERS,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch cohorts: ${res.status}`);
  }
  return res.json();
}

export async function getCohort(id: string): Promise<CohortOut> {
  const res = await fetch(`${API_URL}/cohorts/${encodeURIComponent(id)}`, {
    cache: "no-store",
    headers: API_HEADERS,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch cohort: ${res.status}`);
  }
  return res.json();
}

export async function getCohortEvidence(id: string): Promise<CohortEvidenceOut> {
  const res = await fetch(`${API_URL}/cohorts/${encodeURIComponent(id)}/evidence`, {
    cache: "no-store",
    headers: API_HEADERS,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch cohort evidence: ${res.status}`);
  }
  return res.json();
}

export type ComplaintBucketOut = { bucket_start: string; count: number };

export type AnomalyWindowOut = { anomaly_id: string; metric: string; start_at: string; end_at: string; peak_score: number };

export type CohortTimelineOut = {
  cohort_id: string;
  complaint_buckets: ComplaintBucketOut[];
  anomaly_windows: AnomalyWindowOut[];
};

export async function getCohortTimeline(id: string): Promise<CohortTimelineOut> {
  const res = await fetch(`${API_URL}/cohorts/${encodeURIComponent(id)}/timeline`, {
    cache: "no-store",
    headers: API_HEADERS,
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch cohort timeline: ${res.status}`);
  }
  return res.json();
}

export type Complaint = {
  complaint_id: string;
  customer_id: string;
  received_at: string;
  channel: string;
  text: string;
  product: string;
  region: string;
};

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function fetchComplaints(): Promise<Complaint[]> {
  const res = await fetch(`${API_URL}/complaints`, {
    cache: "no-store",
    headers: { "X-Demo-User": "demo-agent" },
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch complaints: ${res.status}`);
  }
  return res.json();
}

export type VizPoint = {
  complaint_id: string;
  x: number;
  y: number;
  cohort_id: string | null;
  symptom_cluster_id: string | null;
  claimed_cause: string | null;
};

export type VizComplaints = {
  run_id: string;
  dataset_profile: string;
  synthetic: boolean;
  points: VizPoint[];
};

export async function fetchVizComplaints(): Promise<VizComplaints | null> {
  const res = await fetch(`${API_URL}/viz/complaints`, {
    cache: "no-store",
    headers: { "X-Demo-User": "demo-agent" },
  });
  if (res.status === 404) {
    return null; // no pipeline run yet
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch viz complaints: ${res.status}`);
  }
  return res.json();
}

// Action-panel fetchers (Task 12): no hardcoded X-Demo-User header, so the
// `demo_user` cookie set by the DemoUserSwitcher governs identity on the API
// (api/auth.py::current_user reads the header first, falling back to the
// cookie — omitting the header here is required for user-switching to work).
// `credentials: "include"` sends that cookie cross-origin to the API.

export async function confirmCohort(id: string): Promise<CohortOut> {
  const res = await fetch(`${API_URL}/cohorts/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to confirm cohort: ${res.status}`);
  }
  return res.json();
}

export type ComplaintIn = {
  run_id: string;
  complaint_id: string;
  customer_id: string;
  received_at: string;
  channel: string;
  text: string;
  product: string;
  region: string;
  node_id: string;
};

export type ComplaintIngestOut = { complaint_id: string; needs_review: boolean; embedded: boolean };

export async function ingestComplaint(body: ComplaintIn): Promise<ComplaintIngestOut> {
  const res = await fetch(`${API_URL}/complaints`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Failed to ingest complaint: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export type CohortAssignmentOut = { complaint_id: string; assigned: boolean; cohort_id: string | null; similarity: number | null };

export async function assignCohort(complaintId: string, runId: string): Promise<CohortAssignmentOut> {
  const res = await fetch(`${API_URL}/complaints/${encodeURIComponent(complaintId)}/cohort-assignment?run_id=${encodeURIComponent(runId)}`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to assign cohort: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export async function runCohortRemedy(id: string, policyRuleId: string): Promise<{ cohort_id: string; computed: number; routed_to_individual_review: number; remedy_ids: string[] }> {
  const res = await fetch(`${API_URL}/cohorts/${encodeURIComponent(id)}/remedy?policy_rule_id=${encodeURIComponent(policyRuleId)}`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to compute remedy: ${res.status}`);
  }
  return res.json();
}

export async function draftLetter(remedyId: string): Promise<{ remedy_id: string; drafted: boolean }> {
  const res = await fetch(`${API_URL}/remedies/${encodeURIComponent(remedyId)}/drafts`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to draft letter: ${res.status}`);
  }
  return res.json();
}

export async function runGate(remedyId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_URL}/remedies/${encodeURIComponent(remedyId)}/gate`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to run gate: ${res.status}`);
  }
  return res.json();
}

export async function approveRemedy(remedyId: string): Promise<{ remedy_id: string; decision: string; approver_user_id: string; role: string; decided_at: string }> {
  const res = await fetch(`${API_URL}/remedies/${encodeURIComponent(remedyId)}/approve`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to approve remedy: ${res.status}`);
  }
  return res.json();
}
