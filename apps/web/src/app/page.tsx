import { fetchComplaints, fetchVizComplaints } from "@/lib/api";
import { ComplaintScatter } from "@/components/complaint-scatter";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default async function Home() {
  const [complaints, viz] = await Promise.all([fetchComplaints(), fetchVizComplaints()]);

  return (
    <main className="p-8">
      {viz && viz.points.length > 0 ? (
        <section className="mb-8">
          <h2 className="text-xl font-semibold mb-1">
            {viz.dataset_profile} run {viz.run_id} — {viz.points.length} points{" "}
            <span className="text-sm font-normal text-muted-foreground">
              (synthetic — symptom/embedding view, not a verified root cause)
            </span>
          </h2>
          <ComplaintScatter points={viz.points} />
        </section>
      ) : null}
      <h1 className="text-2xl font-semibold mb-4">
        Backtrace — {complaints.length} complaints (tiny)
      </h1>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Received</TableHead>
            <TableHead>Channel</TableHead>
            <TableHead>Product</TableHead>
            <TableHead>Region</TableHead>
            <TableHead>Text</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {complaints.map((c) => (
            <TableRow key={c.complaint_id}>
              <TableCell>{new Date(c.received_at).toLocaleString()}</TableCell>
              <TableCell>{c.channel}</TableCell>
              <TableCell>{c.product}</TableCell>
              <TableCell>{c.region}</TableCell>
              <TableCell>{c.text}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </main>
  );
}
