import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs, Tab } from "./Tabs";

describe("Tabs", () => {
  const mockTabs: Tab[] = [
    { id: "tab1", label: "Tab 1", content: <div>Content 1</div> },
    { id: "tab2", label: "Tab 2", content: <div>Content 2</div> },
    { id: "tab3", label: "Tab 3", content: <div>Content 3</div> },
  ];

  test("renders all tabs", () => {
    render(<Tabs tabs={mockTabs} />);

    expect(screen.getByText("Tab 1")).toBeInTheDocument();
    expect(screen.getByText("Tab 2")).toBeInTheDocument();
    expect(screen.getByText("Tab 3")).toBeInTheDocument();
  });

  test("shows first tab content by default", () => {
    render(<Tabs tabs={mockTabs} />);

    expect(screen.getByText("Content 1")).toBeInTheDocument();
    expect(screen.queryByText("Content 2")).not.toBeInTheDocument();
  });

  test("switches content when tab is clicked", async () => {
    const user = userEvent.setup();
    render(<Tabs tabs={mockTabs} />);

    const tab2 = screen.getByText("Tab 2");
    await user.click(tab2);

    expect(screen.getByText("Content 2")).toBeInTheDocument();
    expect(screen.queryByText("Content 1")).not.toBeInTheDocument();
  });

  test("applies active styles to current tab", async () => {
    const user = userEvent.setup();
    render(<Tabs tabs={mockTabs} />);

    const tab1 = screen.getByText("Tab 1");
    const tab2 = screen.getByText("Tab 2");

    // Tab 1 should be active initially
    expect(tab1).toHaveAttribute("aria-current", "page");
    expect(tab2).not.toHaveAttribute("aria-current");

    // Click Tab 2
    await user.click(tab2);

    // Tab 2 should now be active
    expect(tab2).toHaveAttribute("aria-current", "page");
    expect(tab1).not.toHaveAttribute("aria-current");
  });

  test("uses defaultTab prop when provided", () => {
    render(<Tabs tabs={mockTabs} defaultTab="tab2" />);

    expect(screen.getByText("Content 2")).toBeInTheDocument();
    expect(screen.queryByText("Content 1")).not.toBeInTheDocument();
  });

  test("calls onChange callback when tab changes", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();
    render(<Tabs tabs={mockTabs} onChange={handleChange} />);

    const tab2 = screen.getByText("Tab 2");
    await user.click(tab2);

    expect(handleChange).toHaveBeenCalledWith("tab2");
  });

  test("has proper accessibility attributes", () => {
    render(<Tabs tabs={mockTabs} />);

    const nav = screen.getByRole("navigation", { name: "Tabs" });
    expect(nav).toBeInTheDocument();
  });
});
