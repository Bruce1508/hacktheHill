import { EvidenceTimeline } from "@/components/evidence-timeline";
import { getCohort, getCohortEvidence, getCohortTimeline } from "@/lib/api";

export default async function CohortDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [cohort, evidence, timeline] = await Promise.all([getCohort(id), getCohortEvidence(id), getCohortTimeline(id)]);

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
      <EvidenceTimeline complaintBuckets={timeline.complaint_buckets} anomalyWindows={timeline.anomaly_windows} />
      {/* Task 12 renders the remedy/letter/gate/approve panel here, using `evidence` (hypothesis citations, sample complaint ids) */}
    </main>
  );
}
