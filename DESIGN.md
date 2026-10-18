---
name: Backtrace
description: Bright, evidence-first complaint operations with optical precision.
colors:
  signal-red: "#e30613"
  signal-red-dark: "#a6000a"
  signal-red-bright: "#ff3347"
  signal-red-wash: "#fff2f3"
  paper: "#ffffff"
  field: "#f4f5f6"
  ink: "#111111"
  muted-ink: "#62676d"
  construction-rule: "#d7dadd"
  soft-rule: "#e8eaec"
  unspecified-point: "#a4a8ad"
typography:
  display:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "clamp(2.15rem, 4vw, 4.65rem)"
    fontWeight: 600
    lineHeight: 0.88
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "1.38rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Geist, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "normal"
rounded:
  square: "0"
  circular: "50%"
spacing:
  hairline: "1px"
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "18px"
  xl: "28px"
  section: "72px"
components:
  navigation-rail:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.square}"
    width: "72px"
  signal-field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    height: "500px"
  evidence-tooltip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "12px 14px"
  interpretation-rail:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "24px 0 24px 28px"
  ledger-record:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "15px 14px"
---

# Design System: Backtrace

## Overview

**Creative North Star: "The Optical Evidence Desk"**

Backtrace is a bright operations interface with the character of an incident postmortem in progress. White paper, black ink, cool construction rules, and tightly controlled Ciena-inspired red make a large evidence set feel inspectable rather than theatrical. The system is dense, exact, and calm: hierarchy comes from typography, alignment, and rules instead of cards or decoration.

The world is organized around evidence before interpretation. A complaint field presents symptom proximity, an interpretation rail explains its limits, and a ruled ledger exposes individual records. Visual emphasis must never turn proximity, a customer claim, or an embedding cluster into a verified root cause.

**Key Characteristics:**

- Bright white working surface with black structural anchors
- Condensed operational headings paired with compact, readable body text
- Flat paper and hairline rules instead of elevated cards
- Red reserved for signal, selection, focus, and current state
- Evidence-first responsive records that preserve meaning on narrow screens

## Colors

The palette is true black and bright paper, cooled by neutral greys and interrupted only by a disciplined signal red.

### Primary

- **Ciena Signal Red** (`signal-red`): Marks the active navigation position, claimed-cause points, dataset status, focus outlines, and the strongest evidence accents. It signals attention, never certainty.
- **Boundary Red** (`signal-red-dark`): Carries cautionary boundary labels and text accents that need stronger contrast.
- **Focus Red** (`signal-red-bright`): Supports point-level interaction and highlighted signal detail.
- **Signal Wash** (`signal-red-wash`): Appears only as a quiet row-hover surface behind evidence.

### Neutral

- **Evidence Paper** (`paper`): The default page, rail, tooltip, and ledger surface.
- **Projection Field** (`field`): Separates the plotted evidence plane from paper without creating elevation.
- **True Ink** (`ink`): Primary text, navigation structure, major rules, and related-language points.
- **Cool Muted Ink** (`muted-ink`): Supporting copy, labels, instructions, and secondary metadata.
- **Construction Rule** (`construction-rule`): Primary dividers, field borders, and sequence connectors.
- **Soft Rule** (`soft-rule`): Dense ledger row separation and scrollbar tracks.
- **Unspecified Grey** (`unspecified-point`): Points without a claimed-cause label.

### Named Rules

**The Red Is Signal Rule.** Red is reserved for live attention, current state, focus, or an explicitly labelled claim; it never decorates empty space or implies verified causality.

**The Paper Stays Bright Rule.** Core work surfaces remain white or cool field grey. Do not introduce dark content cards, gradients, glass, or tinted dashboard panels.

## Typography

**Display Font:** Barlow Condensed (with sans-serif fallback)  
**Body Font:** Geist (with sans-serif fallback)  
**Label/Mono Font:** Geist; use tabular numerals for counts, timestamps, and step markers.

**Character:** Barlow Condensed gives run IDs and section headings the clipped authority of an operations document. Geist keeps dense evidence, metadata, and explanatory copy neutral and highly legible.

### Hierarchy

- **Display** (600, fluid `display` token, 0.88): Run identifiers and the strongest page-level operational fact.
- **Headline** (700, `headline` token): Section titles, interpretation headings, and tooltip identifiers.
- **Body** (400, `body` token): Complaint text, interpretation, and supporting descriptions; constrain explanatory passages to roughly 29–52 characters where the layout permits.
- **Label** (650, `label` token): Navigation, legends, facts, counts, and compact metadata.

### Named Rules

**The Condensed Authority Rule.** Use Barlow Condensed for headings and operational identifiers, not paragraphs or dense table evidence.

**The Numbers Align Rule.** Use tabular numerals wherever values are compared vertically or scanned as operational facts.

## Layout

Desktop uses a sticky 72px black navigation rail and a centered workspace capped at 1680px, with 36px side padding. The first evidence workspace is a two-column composition: a flexible complaint field and a 270–330px interpretation rail. Major regions are joined by shared top and bottom rules rather than separated into cards. The complaint ledger begins after a deliberate 72px section interval.

At 1120px, the interpretation rail tightens and the run masthead stacks. At 820px, navigation becomes a 58px horizontal bar, the workspace becomes a single column, and the field height reduces to 420px. At 520px, the 360px field remains interactive and the ledger transforms from a wide table into evidence-first records: complaint text leads, while received time, region, product, and channel follow as labelled metadata. Columns disappear or recompose by information priority; they do not shrink into illegibility.

**The Evidence Topology Rule.** Preserve the sequence complaint field → interpretation rail → complaint ledger. The rail explains the field; it does not compete with it.

**The Mobile Evidence-First Rule.** On narrow screens, lead every record with the complaint itself and retain explicit labels for all metadata.

## Elevation & Depth

The system is flat by design. It uses no shadows, glow, blur, or floating glass. Depth comes from paper-versus-field tone, black and grey hairline rules, dense-to-open spacing, and a red top edge on the tooltip and interpretation boundary. Interactive emphasis is expressed through stroke, color, and focus outline rather than lift.

### Named Rules

**The Ruled Paper Rule.** Separate information with shared rules and tonal planes; do not wrap every section in a raised card.

## Shapes

The form language is rectangular and mechanically precise. Navigation, evidence fields, tooltips, ledger rows, and content regions use square corners. Circles are functional exceptions only: scatter points, legend keys, and numbered interpretation steps. Borders are predominantly 1px; the tooltip uses a 3px red top rule, active navigation uses a 3px red indicator, and keyboard focus uses a 2px red outline offset by 3px.

## Components

### Navigation

- **Shape:** A square black rail (72px desktop) that becomes a horizontal bar (58px) below 820px.
- **State:** Inactive labels are translucent white; hover and current state become paper white. Current state is identified by a 3px red edge, vertical on desktop and horizontal on mobile.
- **Accessibility:** Use semantic navigation landmarks, descriptive labels, and `aria-current="page"` for the active destination.

### Complaint Field

- **Character:** A cool-grey evidence plane with faint orthogonal construction lines and no decorative chart chrome.
- **Points:** Red denotes a claimed cause, black denotes related language, and grey denotes unspecified. A white stroke keeps dense points separable.
- **Interaction:** Drag pans, scroll zooms, and hover inspects. The cursor changes to grab, grabbing, or crosshair to reveal affordance.
- **Boundary:** Adjacent copy must state that proximity reflects language and extracted symptoms, not verified cause.

### Evidence Tooltip

- **Shape:** Square paper panel with a 1px black border and 3px red top rule.
- **Content:** Complaint identifier first, claimed cause second, then a ruled caution that the claim requires operational verification.
- **State:** Hovered points gain a larger white halo with a red outline. The tooltip is a polite status message and does not capture pointer input.

### Interpretation Sequence

- **Character:** A red-ruled reading rail that moves from complaint language to symptom proximity to operational evidence.
- **Shape:** Small numbered circles joined by a neutral hairline, with a final ruled boundary note.
- **Copy:** Use direct, operational language. Explicitly distinguish what the projection shows from what the system has not verified.

### Complaint Ledger

- **Desktop:** A full-width fixed-layout table with quiet headers, ruled rows, stable metadata widths, and complaint text allowed the remaining space.
- **Hover:** Apply only the signal wash and a dark-red timestamp; do not add lift.
- **Mobile:** Replace the header row with per-record labels and a two-column metadata grid. Complaint text spans the full record and appears first.
- **Accessibility:** Keep the table caption available to assistive technology, use scoped column headers, and preserve semantic time values.

### Global Interaction

- **Focus:** Every keyboard-focusable element receives a clearly visible red outline.
- **Motion:** Smooth scrolling is the only ambient motion. Under reduced-motion preference, disable smooth scrolling and collapse animation and transition durations.

## Do's and Don'ts

### Do:

- **Do** lead with observable evidence and place interpretation immediately beside or after it.
- **Do** use red sparingly for current state, focus, claimed-cause signal, and explicit boundaries.
- **Do** preserve semantic landmarks, captions, headings, labels, and visible keyboard focus.
- **Do** recompose dense tables into complaint-first labelled records below 520px.
- **Do** keep synthetic-data provenance visible in the masthead or equivalent page context.

### Don't:

- **Don't** describe embedding proximity, point color, or a claimed cause as verified root cause.
- **Don't** introduce gradients, glass effects, glow, shadows, decorative badges, or interchangeable metric-card grids.
- **Don't** use red as a general brand fill across large surfaces or as proof of certainty.
- **Don't** compress desktop columns until evidence becomes unreadable; stack or recompose by priority.
- **Don't** imply that cohort review, remedies, approvals, or other unimplemented actions are available.
