# Frontend

React 19 with Vite. No router (navigation is by URL hash) and no UI library; styles are in `src/index.css`.

```
npm ci
npm run dev      # http://localhost:5173, forwards /api to the backend on port 8000
npm run lint
npm run build
```

Needs Node 20.19 or newer (22.12 or newer on Node 22). The file layout and how the app fits together are in [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
