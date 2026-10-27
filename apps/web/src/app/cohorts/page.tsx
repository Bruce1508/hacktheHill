import Link from "next/link";

import { fetchLatestRun, listCohorts } from "@/lib/api";

export default async function CohortsPage() {
  const run = await fetchLatestRun();
  const { cohorts } = await listCohorts(run.run_id);

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold mb-4">Cohorts</h1>
      <ul className="space-y-2">
        {cohorts.map((cohort) => (
          <li key={cohort.id}>
            <Link href={`/cohorts/${cohort.id}`} className="block rounded border p-4 hover:bg-neutral-50">
              <div className="flex justify-between">
                <span className="font-medium">{cohort.id}</span>
                <span className="text-sm text-neutral-500">
                  {cohort.status} · {cohort.member_count} members
                </span>
              </div>
              {cohort.hypothesis && <p className="text-sm text-neutral-700 mt-1">{cohort.hypothesis}</p>}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
