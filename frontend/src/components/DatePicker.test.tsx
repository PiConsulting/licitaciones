import { fireEvent, render, screen } from "@testing-library/react";

import { DatePicker } from "./DatePicker";

describe("DatePicker con fechas marcadas", () => {
  it("resalta los días con eventos y muestra sus nombres", () => {
    render(
      <DatePicker
        aria-label="Fecha"
        value="2026-10-05"
        onChange={vi.fn()}
        markedDates={{
          "2026-10-12": ["Adjudicación", "Notificación"],
          "2026-10-20": ["Firma de contrato"],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Fecha" }));

    const marked = screen.getByRole("button", { name: "12: Adjudicación, Notificación" });
    expect(marked).toHaveAttribute("data-marked", "true");
    expect(screen.getByTestId("date-marker-2026-10-12")).toHaveTextContent("Adjudicación");
    expect(screen.getByTestId("date-marker-2026-10-12")).toHaveTextContent("Notificación");
    expect(screen.getByTestId("date-marker-2026-10-20")).toHaveTextContent("Firma de contrato");
    expect(screen.queryByTestId("date-marker-2026-10-13")).not.toBeInTheDocument();
  });

  it("no marca ningún día sin markedDates", () => {
    render(<DatePicker aria-label="Fecha" value="2026-10-05" onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Fecha" }));

    expect(document.querySelector("[data-marked]")).toBeNull();
  });

  it("sigue permitiendo elegir un día marcado", () => {
    const onChange = vi.fn();
    render(
      <DatePicker
        aria-label="Fecha"
        value="2026-10-05"
        onChange={onChange}
        markedDates={{ "2026-10-12": ["Adjudicación"] }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Fecha" }));
    fireEvent.click(screen.getByRole("button", { name: "12: Adjudicación" }));

    expect(onChange).toHaveBeenCalledWith("2026-10-12");
  });
});
