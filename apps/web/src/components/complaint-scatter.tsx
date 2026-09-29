"use client";

import DeckGL from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { OrthographicView, type PickingInfo } from "@deck.gl/core";

import type { VizPoint } from "@/lib/api";

export function ComplaintScatter({ points }: { points: VizPoint[] }) {
  // Fit the initial view to the point cloud — PCA coordinates have no fixed
  // scale, so a hard-coded zoom would clip or dwarf the points.
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const extent = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1e-6);
  const target: [number, number, number] = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, 0];
  const zoom = Math.log2(500 / extent);

  const layer = new ScatterplotLayer<VizPoint>({
    id: "complaints",
    data: points,
    getPosition: (d) => [d.x, d.y],
    getRadius: 4,
    radiusUnits: "pixels",
    getFillColor: [96, 165, 250, 180],
    pickable: true,
  });

  return (
    <DeckGL
      views={new OrthographicView({ id: "ortho" })}
      initialViewState={{ target, zoom }}
      controller
      layers={[layer]}
      getTooltip={({ object }: PickingInfo<VizPoint>) =>
        object ? `${object.complaint_id}\nclaimed cause: ${object.claimed_cause ?? "unspecified"}` : null
      }
      style={{ position: "relative", width: "100%", height: "500px" }}
    />
  );
}
