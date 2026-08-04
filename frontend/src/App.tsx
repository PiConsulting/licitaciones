import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import AnalysisDetail from "./pages/AnalysisDetail";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import NewAnalysisWizard from "./pages/NewAnalysis/NewAnalysisWizard";
import Register from "./pages/Register";

function ProtectedRoute({ children }: { children: ReactElement }) {
  const token = localStorage.getItem("access_token");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
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
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/analyze" element={<NewAnalysisWizard />} />
        <Route path="/analysis/:analysisId" element={<AnalysisDetail />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
