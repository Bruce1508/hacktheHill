"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { OrthographicView, type PickingInfo } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";

import type { VizPoint } from "@/lib/api";

import styles from "./complaint-scatter.module.css";

const POINT_COLORS: [number, number, number, number][] = [
  [227, 6, 19, 220],
  [17, 17, 17, 205],
  [112, 118, 124, 190],
  [255, 51, 71, 185],
];

type HoveredPoint = {
  point: VizPoint;
  x: number;
  y: number;
};

function colorForClaim(claimedCause: string | null): [number, number, number, number] {
  if (!claimedCause) return [164, 168, 173, 170];

  let hash = 0;
  for (const character of claimedCause) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return POINT_COLORS[hash % POINT_COLORS.length];
}

export function ComplaintScatter({ points }: { points: VizPoint[] }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [plotSize, setPlotSize] = useState(400);
  const [containerWidth, setContainerWidth] = useState(300);
  const [hovered, setHovered] = useState<HoveredPoint | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const updatePlotSize = () => {
      const nextSize = Math.max(240, Math.min(root.clientWidth, root.clientHeight) * 0.82);
      setContainerWidth(root.clientWidth);
      setPlotSize((current) => (Math.abs(current - nextSize) < 1 ? current : nextSize));
    };
    const observer = new ResizeObserver(updatePlotSize);
    observer.observe(root);
    updatePlotSize();

    return () => observer.disconnect();
  }, []);

  const { centerX, centerY, extent } = useMemo(() => {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    return {
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
      extent: Math.max(maxX - minX, maxY - minY, 1e-6),
    };
  }, [points]);

  if (points.length === 0) return null;

  const scale = plotSize / extent;
  const tooltipLeft = hovered
    ? Math.max(16, Math.min(hovered.x + 16, containerWidth - 276))
    : 0;
  const positionFor = (point: VizPoint): [number, number] => [
    (point.x - centerX) * scale,
    (point.y - centerY) * scale,
  ];
  const layers = [
    new ScatterplotLayer<VizPoint>({
      id: "complaints",
      data: points,
      getPosition: positionFor,
      getRadius: 3.5,
      radiusUnits: "pixels",
      radiusMinPixels: 2,
      radiusMaxPixels: 6,
      getFillColor: (point) => colorForClaim(point.claimed_cause),
      getLineColor: [255, 255, 255, 170],
      lineWidthMinPixels: 0.5,
      stroked: true,
      pickable: true,
      updateTriggers: { getPosition: [scale, centerX, centerY] },
    }),
    hovered
      ? new ScatterplotLayer<VizPoint>({
          id: "complaint-focus",
          data: [hovered.point],
          getPosition: positionFor,
          getRadius: 9,
          radiusUnits: "pixels",
          getFillColor: [255, 255, 255, 45],
          getLineColor: [227, 6, 19, 255],
          lineWidthMinPixels: 2,
          stroked: true,
          pickable: false,
          updateTriggers: { getPosition: [scale, centerX, centerY] },
        })
      : null,
  ].filter(Boolean);

  return (
    <div className={styles.root} ref={rootRef}>
      <DeckGL
        views={new OrthographicView({ id: "ortho" })}
        initialViewState={{ target: [0, 0, 0], zoom: 0 }}
        controller
        layers={layers}
        onHover={(info: PickingInfo<VizPoint>) =>
          setHovered(info.object ? { point: info.object, x: info.x, y: info.y } : null)
        }
        getCursor={({ isDragging, isHovering }) =>
          isDragging ? "grabbing" : isHovering ? "crosshair" : "grab"
        }
        style={{ position: "absolute", inset: "0" }}
      />

      {hovered ? (
        <div
          className={styles.tooltip}
          style={{ left: tooltipLeft, top: hovered.y }}
          role="status"
        >
          <strong>{hovered.point.complaint_id}</strong>
          <span>Claimed cause: {hovered.point.claimed_cause ?? "Unspecified"}</span>
          <small>Claim only · verify with operational evidence</small>
        </div>
      ) : null}
    </div>
  );
}
