import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import LoginPage from "./pages/LoginPage";
import StudyListPage from "./pages/StudyListPage";
import StudyDetailPage from "./pages/StudyDetailPage";
import AgentFormPage from "./pages/AgentFormPage";
import SessionListPage from "./pages/SessionListPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import SettingsPage from "./pages/SettingsPage";
import InterviewPage from "./pages/InterviewPage";

/**
 * Route guard that redirects to /login when auth is enabled
 * and the user is not authenticated.
 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { loading, authEnabled, authenticated } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50/80">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-gray-900" />
      </div>
    );
  }

  if (authEnabled && !authenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { loading, authEnabled, authenticated } = useAuth();

  return (
    <Routes>
      {/* Participant-facing interview widget (no auth required) */}
      <Route path="/interview/:widgetKey" element={<InterviewPage />} />

      {/* Login page */}
      <Route
        path="/login"
        element={
          loading ? (
            <div className="min-h-screen flex items-center justify-center bg-gray-50/80">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-gray-900" />
            </div>
          ) : authEnabled && !authenticated ? (
            <LoginPage />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />

      {/* Admin dashboard (auth required when enabled) */}
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <Routes>
                <Route path="/" element={<StudyListPage />} />
                <Route path="/studies/:studyId" element={<StudyDetailPage />} />
                <Route
                  path="/studies/:studyId/agents/:agentId"
                  element={<AgentFormPage />}
                />
                <Route
                  path="/studies/:studyId/agents/:agentId/sessions"
                  element={<SessionListPage />}
                />
                <Route
                  path="/studies/:studyId/agents/:agentId/sessions/:sessionId"
                  element={<SessionDetailPage />}
                />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

export default App;
