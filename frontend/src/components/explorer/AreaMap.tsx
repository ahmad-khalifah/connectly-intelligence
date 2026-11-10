"use client";

// Interactive boundary map. By default it draws only our own boundary layers on a plain
// background, so it needs no tile service, API key or internet connection. Set
// NEXT_PUBLIC_BASEMAP_STYLE_URL to a MapLibre style URL to add a basemap underneath.

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoJSONSource, Map as MlMap, Popup, StyleSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { FeatureCollection } from "@/lib/api";

const BASEMAP_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE_URL;

const PLAIN_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f1" } }],
};

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

interface Props {
  context: FeatureCollection | null; // outline of the selected area
  subAreas: FeatureCollection | null; // its sub-areas, clickable
  bbox: [number, number, number, number] | null;
  onSelect: (id: number) => void;
}

export default function AreaMap({ context, subAreas, bbox, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const ready = useRef(false);
  const latest = useRef({ context, subAreas, bbox });
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  function draw() {
    const m = map.current;
    if (!m) return;
    const { context, subAreas, bbox } = latest.current;
    (m.getSource("context") as GeoJSONSource | undefined)?.setData(context ?? EMPTY);
    (m.getSource("children") as GeoJSONSource | undefined)?.setData(subAreas ?? EMPTY);
    if (bbox) {
      m.fitBounds(
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ],
        { padding: 24, duration: 600 },
      );
    }
  }

  // Create the map once.
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
        m.addLayer({
          id: "children-fill",
          type: "fill",
          source: "children",
          paint: {
            "fill-color": "#0e6b5c",
            "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.35, 0.12],
          },
        });
        m.addLayer({
          id: "children-line",
          type: "line",
          source: "children",
          paint: { "line-color": "#0e6b5c", "line-width": 1 },
        });
        m.addLayer({
          id: "context-line",
          type: "line",
          source: "context",
          paint: { "line-color": "#13201d", "line-width": 2 },
        });

        let hovered: string | number | undefined;
        m.on("mousemove", "children-fill", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          if (hovered !== undefined) {
            m.setFeatureState({ source: "children", id: hovered }, { hover: false });
          }
          hovered = f.id;
          if (hovered !== undefined) {
            m.setFeatureState({ source: "children", id: hovered }, { hover: true });
          }
          m.getCanvas().style.cursor = "pointer";
          popup?.setLngLat(e.lngLat).setText(String(f.properties?.name ?? "")).addTo(m);
        });
        m.on("mouseleave", "children-fill", () => {
          if (hovered !== undefined) {
            m.setFeatureState({ source: "children", id: hovered }, { hover: false });
          }
          hovered = undefined;
          m.getCanvas().style.cursor = "";
          popup?.remove();
        });
        m.on("click", "children-fill", (e) => {
          popup?.remove();
          const id = e.features?.[0]?.properties?.id;
          if (typeof id === "number") onSelectRef.current(id);
        });
        ready.current = true;
        draw();
      });

      // The side panel changes height as you navigate; keep the canvas and view in step.
      resizeObserver = new ResizeObserver(() => {
        m.resize();
        const { bbox } = latest.current;
        if (ready.current && bbox) {
          m.fitBounds(
            [
              [bbox[0], bbox[1]],
              [bbox[2], bbox[3]],
            ],
            { padding: 24, duration: 0 },
          );
        }
      });
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

  // Keep the latest data; it is drawn as soon as the map is ready, and on every change after.
  useEffect(() => {
    latest.current = { context, subAreas, bbox };
    if (ready.current) draw();
  }, [context, subAreas, bbox]);

  return <div ref={el} className="h-full min-h-[420px] w-full" aria-label="Boundary map" />;
}
