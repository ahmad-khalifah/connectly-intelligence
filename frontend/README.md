# Connectly Intelligence: web app

Next.js 16 (App Router, cache components), TypeScript, Tailwind CSS 4, MapLibre GL.

```bash
npm install
npm run dev          # http://localhost:3000 (expects the API on http://localhost:8000)
npm run lint
npm run typecheck
npm test             # unit tests (Node test runner)
npm run build        # production build (standalone output, used by the Dockerfile)
npm run e2e          # browser tests against a running stack; see e2e/README.md
```

- The browser never calls the API directly. Pages read data on the server with the session
  cookie (`src/lib/server.ts`), and client components go through `/api/backend/...`
  (`src/app/api/backend/[...path]/route.ts`).
- Brand: the official logo is in `public/brand/` (do not edit; see `docs/brand/README.md`), and
  the colours and fonts are in `src/app/globals.css`.
