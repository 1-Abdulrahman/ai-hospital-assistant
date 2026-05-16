// Application root: sets up providers, global UI components, and routing.
//
// Providers mounted here are intentionally high in the tree so they are
// available to all pages and components (toasts, tooltips, react-query cache,
// authentication context, and router).
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { AppLayout } from "@/components/layout/AppLayout";
import { useToast } from "@/hooks/use-toast";
import { useRef } from "react";
import type { UserRole } from "@/api/types";
import LoginPage from "./pages/Login";
import DashboardPage from "./pages/Dashboard";
import BookingsPage from "./pages/Bookings";
import TenantsPage from "./pages/Tenants";
import AuditPage from "./pages/Audit";
import TracesPage from "./pages/Traces";
import SessionsPage from "./pages/Sessions";
import NlpMonitoringPage from "./pages/NlpMonitoring";
import NotFound from "./pages/NotFound";

// React Query client used for caching and background fetching across the app.
// Creating a single client instance at module-level ensures a shared cache.
const queryClient = new QueryClient();

// ProtectedRoute wrapper: ensures the user is authenticated before rendering
// children. If not authenticated, the user is redirected to the login page.
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// RoleRoute wrapper: checks the current user's role against `allowedRoles`.
// If the user's role is not allowed, it shows a single toast notification
// (avoids spamming toasts on repeated renders by tracking `lastBlockedPath`),
// then navigates the user back to `/dashboard`.
function RoleRoute({ allowedRoles, children }: { allowedRoles: UserRole[]; children: React.ReactNode }) {
  const { role } = useAuth();
  const { toast } = useToast();
  const location = useLocation();
  // Track the last blocked path to avoid repeating the same toast every render
  const lastBlockedPath = useRef<string | null>(null);

  if (!allowedRoles.includes(role)) {
    if (lastBlockedPath.current !== location.pathname) {
      // Show an informative, non-blocking toast explaining the restriction
      toast({ title: "Access denied", description: "You do not have access to this page." });
      lastBlockedPath.current = location.pathname;
    }
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

// AppRoutes: centralizes the application's route structure. Routes are
// organized into an authenticated area (wrapped by `ProtectedRoute` and
// rendered inside `AppLayout`) and public routes (login + 404).
function AppRoutes() {
  const { isAuthenticated } = useAuth();
  return (
    <Routes>
      {/* Login route: if already authenticated, redirect to dashboard */}
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />} />

      {/* All authenticated routes use AppLayout which contains navigation, header, etc. */}
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/bookings" element={<BookingsPage />} />
        <Route path="/sessions" element={<SessionsPage />} />

        {/* Admin-only routes are wrapped with RoleRoute to enforce RBAC */}
        <Route path="/tenants" element={<RoleRoute allowedRoles={["ADMIN"]}><TenantsPage /></RoleRoute>} />
        <Route path="/audit" element={<RoleRoute allowedRoles={["ADMIN"]}><AuditPage /></RoleRoute>} />
        <Route path="/traces" element={<RoleRoute allowedRoles={["ADMIN"]}><TracesPage /></RoleRoute>} />
        <Route path="/nlp-monitoring" element={<RoleRoute allowedRoles={["ADMIN"]}><NlpMonitoringPage /></RoleRoute>} />

        {/* Root of authenticated area redirects to dashboard */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>

      {/* Catch-all 404 route */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

// Root App component: provider composition order matters — React Query needs
// to be available before components that use it, TooltipProvider wraps UI
// that uses tooltips, and the AuthProvider provides authentication context
// to routing and pages.
const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      {/* Two toast systems are rendered: the project's Toaster and Sonner
          component. They serve potentially different purposes/styles; both
          are mounted globally so any page can show notifications. */}
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
