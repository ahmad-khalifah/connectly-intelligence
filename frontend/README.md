# Connectly Intelligence — frontend

Next.js 16 (App Router, cache components), TypeScript, Tailwind CSS 4, MapLibre GL.

```bash
npm install
npm run dev        # http://localhost:3000, expects the API on http://localhost:8000
npm run lint
npm run typecheck
npm run build
```

- `src/app/` pages: `/` overview, `/explorer` map explorer, `/data` datasets and gaps.
- `src/lib/api.ts` typed API client (mirrors `backend/connectly/api/schemas.py`).
- `src/components/explorer/AreaMap.tsx` MapLibre map. It draws only Connectly's own
  boundary layers on a plain background, so it needs no tile service or API key. Set
  `NEXT_PUBLIC_BASEMAP_STYLE_URL` to add a free basemap underneath.
- `scripts/copy-maplibre-worker.mjs` copies MapLibre's web worker into `public/` before
  `dev` and `build`. Without it the map renders no data, because the bundler breaks the
  worker's default location.
