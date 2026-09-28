export type Complaint = {
  complaint_id: string;
  customer_id: string;
  received_at: string;
  channel: string;
  text: string;
  product: string;
  region: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
