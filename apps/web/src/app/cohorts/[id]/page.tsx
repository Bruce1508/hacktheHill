import { getCohort, getCohortEvidence } from "@/lib/api";

export default async function CohortDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [cohort, evidence] = await Promise.all([getCohort(id), getCohortEvidence(id)]);

  return (
    <main className="p-8 space-y-6">
      <h1 className="text-2xl font-semibold">{cohort.id}</h1>
      <p className="text-neutral-600">
        {cohort.status} · {cohort.member_count} members
      </p>
      {cohort.hypothesis && (
        <div className="rounded border p-4 bg-neutral-50">
          <p className="font-medium">Hypothesis</p>
          <p>{cohort.hypothesis}</p>
        </div>
      )}
      {/* Task 11 renders <EvidenceTimeline evidence={evidence} /> here */}
      {/* Task 12 renders the remedy/letter/gate/approve panel here */}
    </main>
  );
}
