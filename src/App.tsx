import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/ui/theme-provider";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import HydrateAuth from "@/components/HydrateAuth";
import { useAuthStore } from "@/stores/auth";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Profile from "./pages/Profile";
import NotFound from "./pages/NotFound";
import MyCollections from "./pages/MyCollections";
import MyCollection from "./pages/MyCollection";
import AdminUsers from "./pages/admin/Users";
import AdminCollections from "./pages/admin/Collections";
import AdminCollection from "./pages/admin/Collection";
import AdminDocuments from "./pages/admin/Documents";

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuthStore();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (user?.role !== "admin" && user?.role !== "superadmin") {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function Home() {
  const { user } = useAuthStore();
  if (user?.role === "admin" || user?.role === "superadmin") {
    return <Navigate to="/admin/collections" replace />;
  }
  return <Navigate to="/chat" replace />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider defaultTheme="system" storageKey="rag-theme">
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <HydrateAuth>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Home />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/chat"
                element={
                  <ProtectedRoute>
                    <Chat />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/profile"
                element={
                  <ProtectedRoute>
                    <Profile />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/collections"
                element={
                  <ProtectedRoute>
                    <MyCollections />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/collections/:id"
                element={
                  <ProtectedRoute>
                    <MyCollection />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/users"
                element={
                  <AdminRoute>
                    <AdminUsers />
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/collections"
                element={
                  <AdminRoute>
                    <AdminCollections />
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/collections/:id"
                element={
                  <AdminRoute>
                    <AdminCollection />
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/documents"
                element={
                  <AdminRoute>
                    <AdminDocuments />
                  </AdminRoute>
                }
              />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </HydrateAuth>
        </BrowserRouter>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
