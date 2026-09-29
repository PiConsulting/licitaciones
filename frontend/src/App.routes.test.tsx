import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import App from "./App";

vi.mock("./pages/Login", () => ({ default: () => <div>Login Page</div> }));
vi.mock("./pages/Register", () => ({ default: () => <div>Register Page</div> }));
vi.mock("./pages/Dashboard", () => ({ default: () => <div>Dashboard Page</div> }));
vi.mock("./pages/AnalysisDetail", () => ({ default: () => <div>Analysis Detail Page</div> }));
vi.mock("./pages/NewAnalysis/NewAnalysisWizard", () => ({ default: () => <div>New Analysis Wizard</div> }));
vi.mock("./components/AppLayout", async () => {
  const { Outlet } = await import("react-router-dom");
  return {
    AppLayout: () => <Outlet />,
  };
});

describe("App routes FE1.2", () => {
  beforeEach(() => {
    localStorage.setItem("access_token", "token");
  });

  afterEach(() => {
    localStorage.clear();
  });

  test("resuelve Home en /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
  });
});
