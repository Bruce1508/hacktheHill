"use client";

import ReactECharts from "echarts-for-react";

type ComplaintBucket = { bucket_start: string; count: number };
type AnomalyWindow = { anomaly_id: string; metric: string; start_at: string; end_at: string; peak_score: number };

export function EvidenceTimeline({ complaintBuckets, anomalyWindows }: { complaintBuckets: ComplaintBucket[]; anomalyWindows: AnomalyWindow[] }) {
  const option = {
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "complaints" },
    series: [
      {
        name: "Complaint bursts",
        type: "bar",
        data: complaintBuckets.map((b) => [b.bucket_start, b.count]),
        markArea: {
          itemStyle: { color: "rgba(255, 0, 0, 0.1)" },
          data: anomalyWindows.map((w) => [{ xAxis: w.start_at, name: w.metric }, { xAxis: w.end_at }]),
        },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 320 }} />;
}
