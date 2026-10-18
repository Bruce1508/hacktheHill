# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Complaint operations agents and reviewers investigating a large synthetic telecom complaint backlog during the Hack the Hill 2026 Ciena-track demo.

## Product Purpose

Backtrace turns a noisy complaint backlog into a smaller set of evidence-backed incident cohorts. Success means a reviewer can distinguish what customers say from what caused the issue, inspect the operational evidence, and make fewer consistent human decisions without surrendering approval authority.

## Positioning

Backtrace does not classify or answer tickets one at a time. It combines complaint language with operational events, topology, bursts, and telemetry anomalies, then forms cohorts by shared cause. Semantic similarity assists the process but operational evidence outranks it.

## Operating Context

The current surface is an engineering and demo view. It loads synthetic complaints through FastAPI, plots the latest processed run with deck.gl, and exposes a complaint table for inspection. The full product workflow adds cohort review, cited evidence, deterministic remedies, consistency checks, and human approval as those capabilities ship.

## Capabilities and Constraints

- All displayed complaint data is synthetic and must remain visibly labelled as such.
- The current scatter is a symptom/embedding projection, not a verified root-cause view.
- The production `backtrace` package and database role cannot read the evaluation answer key.
- Gemini is used for structured extraction and embeddings; monetary decisions remain deterministic and human-approved.
- UI work must preserve existing API contracts and must not imply unimplemented cohort, remedy, or approval actions are live.
- The product is a root-cause engine, not a chatbot, CRM, sentiment dashboard, or regulator-score predictor.

## Brand Commitments

- Product name: Backtrace.
- Hack the Hill 2026, Ciena-track context.
- Professional Ciena-inspired visual character with a red, white, and black palette.
- Plain, operational language; confident without hype.
- Avoid generic AI-dashboard styling, decorative gradients, glass panels, repeated metric-card grids, and fabricated product proof.

## Evidence on Hand

- The running `dev-run-2` contains 1,600 synthetic complaint embeddings.
- The current API and dashboard can show the latest run, the full scatter, and up to 100 complaint records.
- Product and architecture truth lives in `Backtrace — Technical Design Doc.md`.
- A real runtime screenshot exists at `docs/assets/backtrace-current-ui.png`.
- No real customer data, production accuracy, regulator-score impact, or business-impact benchmark is available; future UI must not fabricate them.

## Product Principles

1. Show the evidence before the conclusion.
2. Separate customer language from operational cause.
3. Make uncertainty explicit instead of forcing an answer.
4. Keep monetary and high-impact decisions deterministic and human-controlled.
5. Demonstrate only what the current system can prove.

## Accessibility & Inclusion

The web interface must remain keyboard accessible, provide visible focus, maintain readable contrast, respect reduced-motion preferences, and keep dense operational data usable on narrow screens.
