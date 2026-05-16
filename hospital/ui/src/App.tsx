// Toast notification components: two separate toasters for different notification styles
// - Toaster: uses native OS notifications (shadcn/ui)
// - Sonner: uses custom toast library for more styled notifications
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";

// TooltipProvider: enables tooltip functionality throughout the app
import { TooltipProvider } from "@/components/ui/tooltip";

// React Query: manages server state and caching
// QueryClient: the core client that handles all data fetching and caching
// QueryClientProvider: context provider that makes QueryClient available to the entire app
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// React Router: handles client-side routing and navigation
// BrowserRouter: enables routing in the browser
// Routes & Route: define the app's route structure
import { BrowserRouter, Routes, Route } from "react-router-dom";

// Layout and page components
import AppLayout from "@/components/AppLayout";  // Main layout wrapper with header, nav, etc.
import HomePage from "@/pages/HomePage";          // Landing/home page
import SettingsScreen from "@/pages/SettingsScreen";  // User settings page
import ChatWidget from "@/components/ChatWidget";  // Floating chat widget for booking
import NotFound from "@/pages/NotFound";          // 404 error page


// Initialize React Query client with default settings.
// This client handles all data fetching, caching, and background updates throughout the app.
// Stores API responses in memory to avoid redundant requests.
const queryClient = new QueryClient();

// Root app component: sets up all providers and routing.
// Provider order matters (from outside to inside):
// 1. QueryClientProvider - wraps everything to provide React Query client to all components
// 2. TooltipProvider - enables tooltip functionality
// 3. Toaster components - set up both notification systems
// 4. BrowserRouter - enables routing
// 5. AppLayout - main layout wrapper
// 6. Routes - app's routing structure
// 7. ChatWidget - floating widget rendered at root level (accessible from any page)
const App = () => (
  {/* React Query Provider: makes queryClient available to all components.
      Enables hooks like useQuery, useMutation for data fetching. */}
  <QueryClientProvider client={queryClient}>
    {/* Tooltip Provider: enables tooltip functionality for the entire app */}
    <TooltipProvider>
      {/* Toast notification systems */}
      {/* Toaster: UI framework native notifications */}
      <Toaster />
      {/* Sonner: custom styled toast notifications (used in ChatWidget for feedback) */}
      <Sonner />
      
      {/* Browser Router: enables client-side routing and navigation */}
      <BrowserRouter>
        {/* Main layout wrapper: contains header, navigation, and page content area */}
        <AppLayout>
          {/* Route definitions: map URL paths to page components */}
          <Routes>
            {/* Home/landing page: main entry point where users start */}
            <Route path="/" element={<HomePage />} />
            
            {/* Settings page: user preferences and configuration */}
            <Route path="/settings" element={<SettingsScreen />} />
            
            {/* 404 fallback: shown when URL doesn't match any defined route */}
            <Route path="*" element={<NotFound />} />
          </Routes>
          
          {/* Chat widget: floating button for booking appointments.
              Placed at root level so it's accessible from every page.
              Renders as a fixed floating button in bottom-right corner. */}
          <ChatWidget />
        </AppLayout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
