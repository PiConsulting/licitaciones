import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "../components/ToastContainer";
import Dashboard from "./Dashboard";
import { useAnalysesQuery } from "../features/analysis/hooks/useAnalysesQuery";
import { useAnalysisFilters } from "../features/analysis/hooks/useAnalysisFilters";

vi.mock("../features/analysis/hooks/useAnalysesQuery", () => ({
  useAnalysesQuery: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Dashboard", () => {
  test("muestra estado vacío con CTA al wizard", () => {
    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 0, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Todavía no hay análisis")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ir al wizard de upload/i })).toBeInTheDocument();
  });
});

describe("useAnalysisFilters", () => {
  test("aplica debounce de 300ms en búsqueda", () => {
    vi.useFakeTimers();

    function Probe() {
      const { searchInput, setSearchInput, filters } = useAnalysisFilters();
      return (
        <>
          <input
            aria-label="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
          <span data-testid="debounced-search">{filters.search ?? ""}</span>
        </>
      );
    }

    render(<Probe />);

    fireEvent.change(screen.getByLabelText("search"), { target: { value: "pliego salud" } });
    expect(screen.getByTestId("debounced-search").textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(screen.getByTestId("debounced-search").textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId("debounced-search").textContent).toBe("pliego salud");

    vi.useRealTimers();
  });
});
