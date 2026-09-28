import { fetchComplaints } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default async function Home() {
  const complaints = await fetchComplaints();

  return (
    <main className="p-8">
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
