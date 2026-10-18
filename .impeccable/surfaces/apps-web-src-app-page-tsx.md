---
version: 1
slug: "apps-web-src-app-page-tsx"
primary_target: "apps/web/src/app/page.tsx"
related_targets: ["apps/web/src/components/complaint-scatter.tsx","apps/web/src/app/globals.css"]
---

# Backtrace dashboard

Mode: Operate

Audience: complaint operations agents and reviewers.

Task: understand the latest synthetic complaint run, inspect the embedding field, and scan the complaint ledger without mistaking symptom proximity for verified root cause.

Constraints: preserve the existing API and real runtime data; label synthetic data; do not expose unimplemented cohort, remedy, or approval actions.

## Direction contract

THESIS: Treat the surface as an incident postmortem in progress: one evidence field, one interpretation rail, one complaint ledger. Refuse the generic SaaS dashboard of interchangeable metric cards.

OWN-WORLD: Ciena-inspired optical precision. White paper, true black ink, cool grey construction lines, and Ciena red reserved for signal and active state. Tight rectangular geometry, restrained radii, no gradients, glass, glow, or decorative badges.

STORY: The operator sees the run, understands exactly what the projection means, reads the signal field, then moves into individual complaint evidence. Copy states uncertainty plainly.

FIRST VIEWPORT: A narrow black navigation rail anchors the left. A concise run masthead spans the top. The dominant complaint field occupies roughly two thirds of the workspace; a red-ruled interpretation column occupies the rest. The complaint ledger begins visibly below the fold.

FORM: Incident postmortem timeline, grounded candidate 5 assigned by seed `9f6b8cc7`. Signature interaction: point-level tooltip in a cause-coded red, black, and grey field. Responsive columns disappear by information priority rather than shrinking into illegibility.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
