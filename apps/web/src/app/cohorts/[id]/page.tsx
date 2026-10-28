import { CohortActionPanel } from "@/components/cohort-action-panel";
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
      <div className="rounded border p-4 space-y-3">
        <p className="font-medium">Evidence</p>
        <div>
          <p className="text-sm text-neutral-500">Score components</p>
          <ul className="text-sm">
            {Object.entries(evidence.score_components).map(([key, value]) => (
              <li key={key}>
                {key}: {value.toFixed(2)}
              </li>
            ))}
          </ul>
        </div>
        {evidence.hypothesis_citations && (
          <div>
            <p className="text-sm text-neutral-500">Citations</p>
            <p className="text-sm">
              {evidence.hypothesis_citations.complaint_ids.length} complaint(s) · {evidence.hypothesis_citations.event_ids.length} event(s) ·{" "}
              {evidence.hypothesis_citations.anomaly_ids.length} anomaly window(s)
            </p>
          </div>
        )}
        <div>
          <p className="text-sm text-neutral-500">Topology scope</p>
          <p className="text-sm">
            {evidence.linked_event_ids.length} linked event(s) · {evidence.linked_anomaly_ids.length} linked anomaly window(s)
          </p>
        </div>
        {evidence.sample_complaint_ids.length > 0 && (
          <div>
            <p className="text-sm text-neutral-500">Sample complaints</p>
            <ul className="text-sm">
              {evidence.sample_complaint_ids.map((id) => (
                <li key={id}>{id}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <EvidenceTimeline complaintBuckets={timeline.complaint_buckets} anomalyWindows={timeline.anomaly_windows} />
      <CohortActionPanel cohortId={cohort.id} />
    </main>
  );
}
