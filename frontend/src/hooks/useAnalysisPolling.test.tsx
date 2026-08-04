import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { useAnalysisPolling } from "./useAnalysisPolling";

const mockNavigate = vi.fn();
const mockGetAnalysisStatus = vi.fn();

vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("../api/analyses", () => ({
  getAnalysisStatus: (...args: unknown[]) => mockGetAnalysisStatus(...args),
}));

describe("useAnalysisPolling", () => {
  function buildWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    return function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    };
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("consulta estado mientras está activo", async () => {
    mockGetAnalysisStatus.mockResolvedValue({
      id: "analysis-1",
      status: "analyzing",
      current_stage: "stub_processing",
    });

    const { result } = renderHook(() => useAnalysisPolling("analysis-1", true), {
      wrapper: buildWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data?.status).toBe("analyzing");
    });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test("redirige cuando se completa", async () => {
    mockGetAnalysisStatus.mockResolvedValue({
      id: "analysis-2",
      status: "completed",
      current_stage: null,
    });

    renderHook(() => useAnalysisPolling("analysis-2", true), {
      wrapper: buildWrapper(),
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/analysis/analysis-2");
    });
  });
});
