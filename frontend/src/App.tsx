import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import StudyListPage from "./pages/StudyListPage";
import StudyDetailPage from "./pages/StudyDetailPage";
import AgentFormPage from "./pages/AgentFormPage";
import SessionListPage from "./pages/SessionListPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import InterviewPage from "./pages/InterviewPage";

function App() {
  return (
    <Routes>
      {/* Participant-facing interview widget (no admin layout) */}
      <Route path="/interview/:widgetKey" element={<InterviewPage />} />

      {/* Admin dashboard */}
      <Route
        path="*"
        element={
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
            </Routes>
          </Layout>
        }
      />
    </Routes>
  );
}

export default App;
