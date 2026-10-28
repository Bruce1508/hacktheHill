"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { approveRemedy, confirmCohort, draftLetter, runCohortRemedy, runGate } from "@/lib/api";

const DEFAULT_OUTAGE_POLICY = "policy-outage-credit-v1";

export function CohortActionPanel({ cohortId }: { cohortId: string }) {
  const router = useRouter();
  const [log, setLog] = useState<string[]>([]);
  const [remedyIds, setRemedyIds] = useState<string[]>([]);

  async function run<T>(label: string, action: () => Promise<T>): Promise<T> {
    try {
      const result = await action();
      setLog((prev) => [...prev, `${label}: ${JSON.stringify(result)}`]);
      router.refresh();
      return result;
    } catch (err) {
      setLog((prev) => [...prev, `${label} FAILED: ${String(err)}`]);
      throw err;
    }
  }

  const firstRemedyId = remedyIds[0] ?? null;

  return (
    <div className="space-y-3 rounded border p-4">
      <div className="flex gap-2">
        <button className="px-3 py-1 rounded bg-black text-white" onClick={() => run("confirm", () => confirmCohort(cohortId))}>
          Confirm cohort
        </button>
        <button
          className="px-3 py-1 rounded bg-black text-white"
          onClick={async () => {
            const result = await run("remedy", () => runCohortRemedy(cohortId, DEFAULT_OUTAGE_POLICY));
            setRemedyIds(result.remedy_ids);
          }}
        >
          Compute remedy
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("draft", () => draftLetter(firstRemedyId))}>
          Draft letter
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("gate", () => runGate(firstRemedyId))}>
          Run gate
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("approve", () => approveRemedy(firstRemedyId))}>
          Approve
        </button>
      </div>
      <pre className="text-xs bg-neutral-50 p-2 rounded max-h-40 overflow-auto">{log.join("\n")}</pre>
    </div>
  );
}
