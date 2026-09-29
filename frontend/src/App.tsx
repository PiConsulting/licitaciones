import { useEffect, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import AnalysisDetail from "./pages/AnalysisDetail";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import NewAnalysisWizard from "./pages/NewAnalysis/NewAnalysisWizard";
import Register from "./pages/Register";
import { ChecklistPage } from "./features/checklist/ChecklistPage";
import { useUIStore } from "./store/useUIStore";

function ProtectedRoute({ children }: { children: ReactElement }) {
  const token = localStorage.getItem("access_token");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/analyze" element={<NewAnalysisWizard />} />
        <Route path="/analysis/:analysisId" element={<AnalysisDetail />} />
        <Route path="/analysis/:analysisId/checklist" element={<ChecklistPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
