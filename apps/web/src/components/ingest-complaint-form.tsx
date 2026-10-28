"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { assignCohort, ingestComplaint } from "@/lib/api";

export function IngestComplaintForm({ runId }: { runId: string }) {
  const router = useRouter();
  const [log, setLog] = useState<string[]>([]);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const complaintId = `demo-${Date.now()}`;
    setPending(true);
    try {
      const ingested = await ingestComplaint({
        run_id: runId,
        complaint_id: complaintId,
        customer_id: String(form.get("customer_id")),
        received_at: new Date().toISOString(),
        channel: String(form.get("channel")),
        text: String(form.get("text")),
        product: String(form.get("product")),
        region: String(form.get("region")),
        node_id: String(form.get("node_id")),
      });
      setLog((prev) => [...prev, `ingested ${complaintId}: ${JSON.stringify(ingested)}`]);

      if (ingested.embedded) {
        const assigned = await assignCohort(complaintId, runId);
        setLog((prev) => [...prev, `assignment: ${JSON.stringify(assigned)}`]);
      }
      router.refresh();
    } catch (err) {
      setLog((prev) => [...prev, `FAILED: ${String(err)}`]);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-3 rounded border p-4 mb-6">
      <h2 className="font-medium">Ingest a new complaint (demo step 10)</h2>
      <form onSubmit={onSubmit} className="grid grid-cols-2 gap-2">
        <input name="customer_id" placeholder="customer_id" required className="border rounded px-2 py-1" />
        <input name="node_id" placeholder="node_id" required className="border rounded px-2 py-1" />
        <input name="product" placeholder="product" required className="border rounded px-2 py-1" />
        <input name="region" placeholder="region" required className="border rounded px-2 py-1" />
        <input name="channel" placeholder="channel" required className="border rounded px-2 py-1" />
        <textarea name="text" placeholder="complaint text" required className="border rounded px-2 py-1 col-span-2" />
        <button type="submit" disabled={pending} className="col-span-2 px-3 py-1 rounded bg-black text-white disabled:opacity-50">
          {pending ? "Submitting…" : "Submit complaint"}
        </button>
      </form>
      <pre className="text-xs bg-neutral-50 p-2 rounded max-h-40 overflow-auto">{log.join("\n")}</pre>
    </div>
  );
}
