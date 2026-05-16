// Application bootstrap (entry point)
//
// - Uses React 18's `createRoot` API to mount the application into the
//   DOM element with id "root". The non-null assertion (!) is used here
//   because the app expects `index.html` to include the root element.
// - Imports global CSS (Tailwind + app styles) so they are applied before
//   any components render.
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Mount the top-level `App` component into the DOM. This is intentionally
// minimal — all provider composition (QueryClient, Router, Auth, etc.) is
// handled inside `App` so the entry point remains focused on bootstrapping.
createRoot(document.getElementById("root")!).render(<App />);
