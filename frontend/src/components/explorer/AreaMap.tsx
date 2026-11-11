"use client";

// Interactive map. By default it draws only our own layers on a plain background, so it needs
// no tile service, API key or internet connection. Set NEXT_PUBLIC_BASEMAP_STYLE_URL to a
// MapLibre style URL to add a basemap underneath.

import "maplibre-gl/dist/maplibre-gl.css";

import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MlMap,
  MapGeoJSONFeature,
  Popup,
  StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { FeatureCollection } from "@/lib/api";
import { NO_DATA } from "@/lib/sectors";

const BASEMAP_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE_URL;

// Fills are opaque on the plain background. MapLibre's polygon triangulation occasionally
// draws a sliver of a complex but valid area twice (seen on Mubi North at state zoom); with
// a translucent fill that shows as a dark wedge, with an opaque fill it is invisible. Over a
// basemap the fill must stay translucent so the basemap shows through.
const FILL_OPACITY_CHOROPLETH = BASEMAP_URL ? 0.8 : 1;
const PLAIN_FILL = "#f6eeee";

const PLAIN_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#f3efea" } }],
};

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface Choropleth {
  values: Map<number, number>;
  stops: number[]; // strictly increasing thresholds
  colors: string[]; // stops.length + 1 colours
  format: (v: number) => string;
}

export interface PointLayer {
  data: GeoJSON.FeatureCollection;
  attribution: string[];
}

interface Props {
  context: FeatureCollection | null;
  subAreas: FeatureCollection | null;
  bbox: [number, number, number, number] | null;
  choropleth: Choropleth | null;
  facilities: PointLayer | null;
  settlements: PointLayer | null;
  onSelect: (id: number) => void;
  onSelectPoint?: (layer: "facilities" | "settlements", id: number) => void;
}

function fillExpression(stops: number[], colors: string[]): ExpressionSpecification {
  const step: unknown[] = ["step", ["feature-state", "value"], colors[0]];
  stops.forEach((b, i) => step.push(b, colors[i + 1]));
  return [
    "case",
    ["==", ["feature-state", "value"], null],
    NO_DATA,
    step,
  ] as unknown as ExpressionSpecification;
}

export default function AreaMap(props: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const ready = useRef(false);
  const latest = useRef(props);
  const appliedIds = useRef<number[]>([]);
  const lastBbox = useRef<string | null>(null);

  function draw() {
    const m = map.current;
    if (!m) return;
    const { context, subAreas, bbox, choropleth, facilities, settlements } = latest.current;
    (m.getSource("context") as GeoJSONSource | undefined)?.setData(context ?? EMPTY);
    (m.getSource("children") as GeoJSONSource | undefined)?.setData(subAreas ?? EMPTY);
    (m.getSource("facilities") as GeoJSONSource | undefined)?.setData(facilities?.data ?? EMPTY);
    (m.getSource("settlements") as GeoJSONSource | undefined)?.setData(settlements?.data ?? EMPTY);

    for (const id of appliedIds.current) m.removeFeatureState({ source: "children", id }, "value");
    appliedIds.current = [];
    if (choropleth && subAreas) {
      for (const f of subAreas.features) {
        const id = (f.properties?.id ?? f.id) as number;
        const v = choropleth.values.get(id);
        m.setFeatureState({ source: "children", id }, { value: v ?? null });
        appliedIds.current.push(id);
      }
      m.setPaintProperty("children-fill", "fill-color", fillExpression(choropleth.stops, choropleth.colors));
      m.setPaintProperty("children-fill", "fill-opacity", FILL_OPACITY_CHOROPLETH);
      // White borders keep neighbours in the same colour class apart.
      m.setPaintProperty("children-line", "line-color", "#ffffff");
      m.setPaintProperty("children-line", "line-opacity", 0.9);
    } else {
      m.setPaintProperty("children-fill", "fill-color", BASEMAP_URL ? "#6b1420" : PLAIN_FILL);
      m.setPaintProperty("children-fill", "fill-opacity", BASEMAP_URL ? 0.06 : 1);
      m.setPaintProperty("children-line", "line-color", "#6b1420");
      m.setPaintProperty("children-line", "line-opacity", 0.55);
    }
    const key = bbox?.join(",") ?? null;
    if (bbox && key !== lastBbox.current) {
      lastBbox.current = key;
      m.fitBounds(
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ],
        { padding: 24, duration: 600 },
      );
    }
  }

  useEffect(() => {
    let cancelled = false;
    let popup: Popup | null = null;
    let resizeObserver: ResizeObserver | null = null;
    (async () => {
      const ml = await import("maplibre-gl");
      if (cancelled || !el.current) return;
      // Served from public/ by scripts/copy-maplibre-worker.mjs (see that file for why).
      ml.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
      const m = new ml.Map({
        container: el.current,
        style: BASEMAP_URL ?? PLAIN_STYLE,
        center: [8.7, 9.1],
        zoom: 5,
        attributionControl: { compact: true },
      });
      m.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new ml.ScaleControl({ unit: "metric" }), "bottom-left");
      popup = new ml.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
      map.current = m;

      m.on("load", () => {
        m.addSource("context", { type: "geojson", data: EMPTY });
        m.addSource("children", {
          type: "geojson",
          data: EMPTY,
          promoteId: "id",
          attribution: "Boundaries © GRID3 (CC BY 4.0) via geoBoundaries",
        });
        m.addSource("facilities", { type: "geojson", data: EMPTY });
        m.addSource("settlements", { type: "geojson", data: EMPTY });
        m.addLayer({
          id: "children-fill",
          type: "fill",
          source: "children",
          paint: { "fill-color": BASEMAP_URL ? "#6b1420" : PLAIN_FILL, "fill-opacity": BASEMAP_URL ? 0.06 : 1 },
        });
        m.addLayer({ id: "children-line", type: "line", source: "children", paint: { "line-color": "#6b1420", "line-width": 0.8, "line-opacity": 0.55 } });
        m.addLayer({ id: "context-line", type: "line", source: "context", paint: { "line-color": "#1f1517", "line-width": 2 } });
        // Hover is shown as an outline, so it works with opaque fills.
        m.addLayer({
          id: "children-hover",
          type: "line",
          source: "children",
          paint: {
            "line-color": "#1f1517",
            "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 2.5, 0],
          },
        });
        m.addLayer({
          id: "settlements-circle",
          type: "circle",
          source: "settlements",
          paint: { "circle-radius": 3, "circle-color": "#d9a441", "circle-stroke-color": "#7f5a12", "circle-stroke-width": 0.6 },
        });
        m.addLayer({
          id: "facilities-circle",
          type: "circle",
          source: "facilities",
          paint: { "circle-radius": 4.5, "circle-color": "#6b1420", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.2 },
        });

        let hovered: string | number | undefined;
        const label = (f: MapGeoJSONFeature) => {
          const name = String(f.properties?.name ?? "");
          const { choropleth } = latest.current;
          if (!choropleth || f.id === undefined) return name;
          const v = choropleth.values.get(f.id as number);
          return `${name}: ${v === undefined ? "no data" : choropleth.format(v)}`;
        };
        m.on("mousemove", "children-fill", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          if (hovered !== undefined) m.setFeatureState({ source: "children", id: hovered }, { hover: false });
          hovered = f.id;
          if (hovered !== undefined) m.setFeatureState({ source: "children", id: hovered }, { hover: true });
          m.getCanvas().style.cursor = "pointer";
          popup?.setLngLat(e.lngLat).setText(label(f)).addTo(m);
        });
        m.on("mouseleave", "children-fill", () => {
          if (hovered !== undefined) m.setFeatureState({ source: "children", id: hovered }, { hover: false });
          hovered = undefined;
          m.getCanvas().style.cursor = "";
          popup?.remove();
        });
        m.on("click", "children-fill", (e) => {
          if (m.queryRenderedFeatures(e.point, { layers: ["facilities-circle", "settlements-circle"] }).length) return;
          popup?.remove();
          const id = e.features?.[0]?.id;
          if (typeof id === "number") latest.current.onSelect(id);
        });
        for (const layer of ["facilities", "settlements"] as const) {
          m.on("mouseenter", `${layer}-circle`, (e) => {
            const p = e.features?.[0]?.properties ?? {};
            m.getCanvas().style.cursor = "pointer";
            const text = [p.name || "(unnamed)", p.subtype || p.kind, p.status].filter(Boolean).join(" · ");
            popup?.setLngLat(e.lngLat).setText(text).addTo(m);
          });
          m.on("mouseleave", `${layer}-circle`, () => {
            m.getCanvas().style.cursor = "";
            popup?.remove();
          });
          m.on("click", `${layer}-circle`, (e) => {
            const id = e.features?.[0]?.properties?.id;
            if (typeof id === "number") latest.current.onSelectPoint?.(layer, id);
          });
        }
        ready.current = true;
        draw();
      });

      resizeObserver = new ResizeObserver(() => m.resize());
      resizeObserver.observe(el.current);
    })();
    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      popup?.remove();
      map.current?.remove();
      map.current = null;
      ready.current = false;
    };
  }, []);

  useEffect(() => {
    latest.current = props;
    if (ready.current) draw();
  });

  return <div ref={el} className="h-full min-h-[460px] w-full" role="region" aria-label="Map of the selected area" />;
}
