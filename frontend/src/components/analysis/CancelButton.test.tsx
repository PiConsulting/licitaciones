import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { CancelButton } from "./CancelButton";

const mockCancelAnalysis = vi.fn();

vi.mock("../../api/analyses", () => ({
  cancelAnalysis: (...args: unknown[]) => mockCancelAnalysis(...args),
}));

describe("CancelButton", () => {
  function Wrapper({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("ejecuta cancelacion al hacer click", async () => {
    mockCancelAnalysis.mockResolvedValue({ status: "cancelled" });

    render(<CancelButton analysisId="analysis-1" />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole("button", { name: /cancelar analisis/i }));

    await waitFor(() => {
      expect(mockCancelAnalysis).toHaveBeenCalledWith("analysis-1");
    });
  });
});
