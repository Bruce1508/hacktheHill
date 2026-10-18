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
