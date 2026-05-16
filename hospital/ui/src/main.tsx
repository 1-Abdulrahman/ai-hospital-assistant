// createRoot: React 18 function that creates a root to render the app into the DOM.
// This replaces the older ReactDOM.render() method and enables concurrent features.
import { createRoot } from "react-dom/client";

// App: root component that contains all providers (React Query, React Router, etc.)
// and the main routing structure for the application.
import App from "./App.tsx";

// Global styles: CSS file that applies base styles and CSS variables to the entire app.
// Includes Tailwind CSS imports and any custom global styling.
import "./index.css";

// Create React root and render the App component into the DOM.
// Process:
// 1. Find the DOM element with id="root" (from index.html)
// 2. Create a React root at that location
// 3. The "!" is a TypeScript non-null assertion (assumes element exists)
// 4. Render the App component into that root element
// 
// The entire app tree (all components, providers, pages) is mounted here.
// From this point, React takes over and manages all UI updates and interactions.
createRoot(document.getElementById("root")!).render(<App />);
