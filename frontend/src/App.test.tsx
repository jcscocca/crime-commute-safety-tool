import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the dashboard shell copy", () => {
    render(<App />);

    expect(screen.getByText("Seattle reported incident context")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Compare places you visit" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/without uploading personal location history/i)
    ).toBeInTheDocument();
  });
});
