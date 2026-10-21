import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBoundary } from "../components/ui/ErrorBoundary";

/** A component that throws while rendering. */
function Boom({ message = "kaboom" }: { message?: string }): never {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  it("renders its children while nothing fails", () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("All good")).toBeInTheDocument();
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });

  it("catches a render error and shows a recoverable panel", () => {
    // React logs the caught error; keep the test output clean.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    const panel = screen.getByTestId("error-boundary");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute("role", "alert");
    // The reason stays visible — a blank screen would hide it.
    expect(screen.getByTestId("error-boundary-message")).toHaveTextContent("kaboom");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();

    consoleError.mockRestore();
  });

  it("calls onError so the app can report the failure", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const onError = vi.fn();

    render(
      <ErrorBoundary onError={onError}>
        <Boom message="render failed" />
      </ErrorBoundary>,
    );

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);

    consoleError.mockRestore();
  });

  it("offers a way back after a failure", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    const retry = screen.getByRole("button", { name: /try again/i });
    await user.click(retry);

    // Retrying re-renders the children, which fail again — the point is that
    // the app is still interactive instead of frozen.
    expect(screen.getByTestId("error-boundary")).toBeInTheDocument();

    consoleError.mockRestore();
  });
});
