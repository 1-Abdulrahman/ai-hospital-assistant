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

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RoleRoute({ allowedRoles, children }: { allowedRoles: UserRole[]; children: React.ReactNode }) {
  const { role } = useAuth();
  const { toast } = useToast();
  const location = useLocation();
  const lastBlockedPath = useRef<string | null>(null);

  if (!allowedRoles.includes(role)) {
    if (lastBlockedPath.current !== location.pathname) {
      toast({ title: "Access denied", description: "You do not have access to this page." });
      lastBlockedPath.current = location.pathname;
    }
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />} />
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/bookings" element={<BookingsPage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/tenants" element={<RoleRoute allowedRoles={["ADMIN"]}><TenantsPage /></RoleRoute>} />
        <Route path="/audit" element={<RoleRoute allowedRoles={["ADMIN"]}><AuditPage /></RoleRoute>} />
        <Route path="/traces" element={<RoleRoute allowedRoles={["ADMIN"]}><TracesPage /></RoleRoute>} />
        <Route path="/nlp-monitoring" element={<RoleRoute allowedRoles={["ADMIN"]}><NlpMonitoringPage /></RoleRoute>} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
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
