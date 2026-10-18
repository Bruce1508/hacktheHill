import { ComplaintScatter } from "@/components/complaint-scatter";
import { fetchComplaints, fetchVizComplaints } from "@/lib/api";

import styles from "./page.module.css";

export default async function Home() {
  const [complaints, viz] = await Promise.all([fetchComplaints(), fetchVizComplaints()]);
  const regionCount = new Set(complaints.map((complaint) => complaint.region)).size;
  const claimedCauseCount = new Set(
    viz?.points.map((point) => point.claimed_cause).filter(Boolean) ?? [],
  ).size;

  return (
    <div className={styles.shell}>
      <aside className={styles.navigation} aria-label="Backtrace navigation">
        <a className={styles.brand} href="#top" aria-label="Backtrace home">
          <span className={styles.brandMark} aria-hidden="true" />
          <span className={styles.brandName}>bt</span>
        </a>

        <nav className={styles.navLinks} aria-label="Workspace sections">
          <a className={styles.navLinkActive} href="#signal-field" aria-current="page">
            <span>Map</span>
          </a>
          <a className={styles.navLink} href="#complaint-ledger">
            <span>Cases</span>
          </a>
        </nav>
      </aside>

      <main className={styles.main} id="top">
        <header className={styles.masthead}>
          <div>
            <h1>Backtrace</h1>
            <p>Complaint intelligence for shared incidents</p>
          </div>
          <div className={styles.contextLabel}>
            <span>Synthetic dataset</span>
            <span>Hack the Hill 2026 · Ciena track</span>
          </div>
        </header>

        <section className={styles.runHeader} aria-labelledby="run-heading">
          <div>
            <h2 id="run-heading">{viz ? viz.run_id : "No processed run"}</h2>
          </div>
          <dl className={styles.runFacts}>
            <div><dt>Profile</dt><dd>{viz?.dataset_profile ?? "Unavailable"}</dd></div>
            <div><dt>Plotted</dt><dd>{viz?.points.length.toLocaleString() ?? "0"}</dd></div>
            <div><dt>Loaded cases</dt><dd>{complaints.length}</dd></div>
            <div><dt>Regions</dt><dd>{regionCount}</dd></div>
          </dl>
        </section>

        <section className={styles.workspace} id="signal-field" aria-labelledby="field-heading">
          <div className={styles.fieldPanel}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 id="field-heading">Complaint field</h2>
                <p>Proximity reflects language and extracted symptoms.</p>
              </div>
              <div className={styles.legend} aria-label="Point color legend">
                <span><i className={styles.legendRed} /> Claimed cause</span>
                <span><i className={styles.legendBlack} /> Related language</span>
                <span><i className={styles.legendGrey} /> Unspecified</span>
              </div>
            </div>

            <div className={styles.scatterFrame}>
              {viz && viz.points.length > 0 ? (
                <ComplaintScatter points={viz.points} />
              ) : (
                <div className={styles.emptyState}>
                  <h3>No projection is available</h3>
                  <p>Complete an extraction, embedding, and layout run to populate this field.</p>
                </div>
              )}
            </div>

            <div className={styles.fieldFooter}>
              <span>{claimedCauseCount} claimed-cause labels visible</span>
              <span>Drag to pan · Scroll to zoom · Hover to inspect</span>
            </div>
          </div>

          <aside className={styles.interpretation} aria-labelledby="interpretation-heading">
            <h2 id="interpretation-heading">Read this view carefully</h2>
            <p className={styles.interpretationLead}>
              This map shows symptom proximity. It does not verify why an incident happened.
            </p>

            <ol className={styles.readingSteps}>
              <li>
                <span>Complaint language</span>
                <p>Customer text is redacted, structured, and embedded before layout.</p>
              </li>
              <li>
                <span>Symptom proximity</span>
                <p>Nearby points describe similar experiences, not necessarily the same cause.</p>
              </li>
              <li>
                <span>Operational evidence</span>
                <p>Telemetry, topology, scope, and time must agree before cohorts become root-cause candidates.</p>
              </li>
            </ol>

            <div className={styles.boundaryNote}>
              <span>Current boundary</span>
              <p>Root-cause linking is not represented in this projection.</p>
            </div>
          </aside>
        </section>

        <section className={styles.ledger} id="complaint-ledger" aria-labelledby="ledger-heading">
          <div className={styles.ledgerHeader}>
            <div>
              <h2 id="ledger-heading">Complaint ledger</h2>
              <p>The first {complaints.length} complaints returned by the API.</p>
            </div>
            <span className={styles.rowCount}>{complaints.length} records</span>
          </div>

          <div className={styles.tableViewport}>
            <table className={styles.table}>
              <caption>Complaints in the current synthetic dataset</caption>
              <thead>
                <tr>
                  <th scope="col">Received</th>
                  <th scope="col">Channel</th>
                  <th scope="col">Product</th>
                  <th scope="col">Region</th>
                  <th scope="col">Complaint</th>
                </tr>
              </thead>
              <tbody>
                {complaints.map((complaint) => (
                  <tr key={complaint.complaint_id}>
                    <td>
                      <time dateTime={complaint.received_at}>
                        {new Date(complaint.received_at).toLocaleString("en-CA", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </time>
                    </td>
                    <td>{complaint.channel}</td>
                    <td>{complaint.product.replaceAll("_", " ")}</td>
                    <td>{complaint.region}</td>
                    <td>{complaint.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className={styles.footer}>
          <span>Backtrace prototype</span>
          <span>Evidence before conclusions</span>
        </footer>
      </main>
    </div>
  );
}
