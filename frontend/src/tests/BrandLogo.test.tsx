import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrandLogo } from "../components/ui/BrandLogo";

describe("BrandLogo Component", () => {
  it("renders the Laqta mark, wordmark and bilingual badge by default", () => {
    render(<BrandLogo />);

    const mark = screen.getByRole("img", { name: "Laqta logo" });
    expect(mark).toBeInTheDocument();

    expect(screen.getByText("Laqta")).toBeInTheDocument();
    expect(screen.getByText("لقطّة")).toBeInTheDocument();
    expect(screen.getByText(/Long Videos/i)).toBeInTheDocument();
    expect(screen.getByText(/Viral Shorts/i)).toBeInTheDocument();
  });

  it("supports hiding subtitle", () => {
    render(<BrandLogo showSubtitle={false} />);

    expect(screen.getByText("Laqta")).toBeInTheDocument();
    expect(screen.queryByText(/Long Videos/i)).not.toBeInTheDocument();
  });

  it("supports hiding all text for icon-only usage", () => {
    render(<BrandLogo showText={false} />);

    expect(screen.getByTestId("laqta-mark")).toBeInTheDocument();
    expect(screen.queryByText("Laqta")).not.toBeInTheDocument();
  });

  it("scales the mark with the requested size", () => {
    const { rerender } = render(<BrandLogo size="sm" />);
    const mark = screen.getByTestId("laqta-mark");
    expect(mark).toHaveAttribute("width", "28");

    rerender(<BrandLogo size="lg" />);
    expect(mark).toHaveAttribute("width", "48");
  });
});
