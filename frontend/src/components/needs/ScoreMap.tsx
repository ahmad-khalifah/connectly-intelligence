"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { clientApi, type FeatureCollection, type Level } from "@/lib/api";
import { classes } from "@/lib/sectors";

const AreaMap = dynamic(() => import("@/components/explorer/AreaMap"), {
  ssr: false,
  loading: () => <div className="h-full min-h-[460px] w-full animate-pulse bg-paper" />,
});

/** Areas coloured by gap score (darker = larger gap). */
export function ScoreMap({ level, scopeId, scores }: { level: Level; scopeId: number; scores: [number, number][] }) {
  const router = useRouter();
  const [shapes, setShapes] = useState<{ key: string; fc: FeatureCollection; outline: FeatureCollection } | null>(null);
  const key = `${level}|${scopeId}`;
  useEffect(() => {
    let stale = false;
    Promise.all([
      clientApi<FeatureCollection>(`/api/v1/geojson?level=${level}&within_id=${scopeId}`),
      clientApi<FeatureCollection>(`/api/v1/areas/${scopeId}/geojson`),
    ]).then(([fc, outline]) => !stale && setShapes({ key, fc, outline }));
    return () => {
      stale = true;
    };
  }, [key, level, scopeId]);
  const current = shapes?.key === key ? shapes : null;
  const bbox = useMemo<[number, number, number, number] | null>(() => {
    if (!current) return null;
    let [x0, y0, x1, y1] = [180, 90, -180, -90];
    const walk = (c: unknown): void => {
      if (Array.isArray(c) && typeof c[0] === "number") {
        x0 = Math.min(x0, c[0] as number);
        x1 = Math.max(x1, c[0] as number);
        y0 = Math.min(y0, c[1] as number);
        y1 = Math.max(y1, c[1] as number);
      } else if (Array.isArray(c)) c.forEach(walk);
    };
    for (const f of current.outline.features) walk((f.geometry as GeoJSON.Polygon).coordinates);
    return [x0, y0, x1, y1];
  }, [current]);
  const choropleth = useMemo(
    () => ({ values: new Map(scores), ...classes([20, 40, 60, 80]), format: (v: number) => `gap score ${v.toFixed(0)}` }),
    [scores],
  );
  return (
    <AreaMap
      context={current?.outline ?? null}
      subAreas={current?.fc ?? null}
      bbox={bbox}
      choropleth={choropleth}
      facilities={null}
      settlements={null}
      onSelect={(id) => router.push(`/areas/${id}`)}
    />
  );
}
