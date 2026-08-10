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
      status: "processing",
      current_stage: "analyzing",
      progress_percentage: 45,
      stage_progress: "Analizando categorias (4 de 8)",
    });

    const { result } = renderHook(() => useAnalysisPolling("analysis-1", true), {
      wrapper: buildWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data?.status).toBe("processing");
    });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test("redirige cuando se completa", async () => {
    const onCompleted = vi.fn();

    mockGetAnalysisStatus.mockResolvedValue({
      id: "analysis-2",
      status: "analyzed",
      current_stage: "completed",
      progress_percentage: 100,
      stage_progress: "Analizado",
    });

    renderHook(() => useAnalysisPolling("analysis-2", true, { onCompleted }), {
      wrapper: buildWrapper(),
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/analysis/analysis-2");
    });
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });
});
