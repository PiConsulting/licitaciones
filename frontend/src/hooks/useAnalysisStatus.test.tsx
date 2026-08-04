import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { useAnalysisStatus } from "./useAnalysisStatus";

const mockGetAnalysisStatus = vi.fn();

vi.mock("../api/analyses", () => ({
  getAnalysisStatus: (...args: unknown[]) => mockGetAnalysisStatus(...args),
}));

describe("useAnalysisStatus", () => {
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

  test("consulta estado de analisis", async () => {
    mockGetAnalysisStatus.mockResolvedValue({
      id: "analysis-1",
      status: "processing",
      current_stage: "analyzing",
      progress_percentage: 40,
      stage_progress: "Analizando categorias (3 de 8)",
    });

    const { result } = renderHook(() => useAnalysisStatus("analysis-1", true), {
      wrapper: buildWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data?.status).toBe("processing");
    });
  });
});
