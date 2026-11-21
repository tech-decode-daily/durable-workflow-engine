import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import Overview from "./pages/Overview";
import { Listings } from "./pages/Lists";
import { Editor } from "./pages/Builder";
import { RunDetails, WorkflowDetails } from "./pages/Details";
import { request } from "./api";

const workflow = {
  id: "w",
  name: "Test pipeline",
  workflow_key: "example",
  status: "active",
  description: "Example",
  latest_version: 1,
  run_count: 2,
  created_at: new Date().toISOString(),
  draft: { name: "Test pipeline", description: "", steps: [] },
};
const run = {
  id: "r",
  status: "FAILED",
  workflow_id: "w",
  workflow_name: "Test pipeline",
  step_count: 1,
  version: 1,
  input_data: { text: "example" },
  output_data: null,
  started_at: null,
  completed_at: null,
  error_message: "Intentional task failure",
};
const page = (items: unknown[]) => ({
  items,
  total: items.length,
  offset: 0,
  limit: 20,
});
function setup(
  component: ReactElement,
  path: string,
  start: string,
  handler: (url: string, method: string, body: unknown) => unknown,
) {
  const fetch = vi.fn(async (url: string, opts: RequestInit = {}) => {
    const body = handler(
      url.replace("/api/v1", ""),
      String(opts.method || "GET"),
      opts.body ? JSON.parse(String(opts.body)) : undefined,
    );
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetch);
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={[start]}>
        <Routes>
          <Route path={path} element={component} />
          <Route path="*" element={<div>Destination</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetch;
}
const registry = [
  {
    task_type: "data.validate_json",
    description: "Validate required fields",
    config_schema: {},
  },
];
describe("workflow console", () => {
  it("renders API dashboard counts and service status", async () => {
    setup(<Overview />, "/", "/", (url) =>
      url.startsWith("/runs")
        ? page([])
        : url.includes("health")
          ? {
              api: "healthy",
              postgres: "healthy",
              redis: "healthy",
              workers: "healthy",
            }
          : {
              total_runs: 42,
              total_workflows: 3,
              running_runs: 0,
              completed_runs: 9,
              failed_runs: 1,
              active_workers: 1,
              pending_tasks: 0,
              running_tasks: 0,
              activity: [],
            },
    );
    expect(await screen.findByText("42")).toBeVisible();
    expect(screen.getByText("90.0%")).toBeVisible();
    expect(await screen.findAllByText("Operational")).toHaveLength(4);
  });
  it("lists workflow versions and filters by text", async () => {
    const fetch = setup(
      <Listings kind="workflows" />,
      "/workflows",
      "/workflows",
      () => page([workflow]),
    );
    expect(await screen.findByText("Test pipeline")).toBeVisible();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "needle" },
    });
    await waitFor(() =>
      expect(fetch.mock.calls.some((c) => c[0].includes("search=needle"))).toBe(
        true,
      ),
    );
  });
  it("validates the editor before a mutation", async () => {
    const fetch = setup(<Editor />, "/new", "/new", () => registry);
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Give the workflow a name",
    );
    expect(fetch.mock.calls.every((c) => c[1]?.method === "GET")).toBe(true);
  });
  it("saves an ordered draft", async () => {
    const fetch = setup(<Editor />, "/new", "/new", (url) =>
      url === "/tasks/registry" ? registry : workflow,
    );
    fireEvent.change(screen.getByLabelText("Workflow name"), {
      target: { value: "Draft example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add step" }));
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByText("Destination");
    const post = fetch.mock.calls.find((c) => c[1]?.method === "POST");
    expect(
      JSON.parse(String(post?.[1]?.body)).steps.map(
        (s: { key: string }) => s.key,
      ),
    ).toEqual(["step_1", "step_2"]);
  });
  it("submits input and an idempotency key when starting a run", async () => {
    const fetch = setup(
      <WorkflowDetails />,
      "/workflows/:workflowId",
      "/workflows/w",
      (url, method) =>
        method === "POST" ? run : url === "/workflows/w" ? workflow : page([]),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Run workflow" }),
    );
    fireEvent.change(screen.getByLabelText("Input JSON"), {
      target: { value: '{"x":42}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start execution" }));
    await screen.findByText("Destination");
    const post = fetch.mock.calls.find((c) => c[1]?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      input_data: { x: 42 },
      idempotency_key: expect.any(String),
    });
  });
  it("renders failed execution and confirms manual retry", async () => {
    const fetch = setup(<RunDetails />, "/runs/:runId", "/runs/r", (url) =>
      url.includes("timeline")
        ? { run, steps: [], events: page([]) }
        : page([]),
    );
    expect(await screen.findByText("Intentional task failure")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Confirm",
      }),
    );
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          (c) => c[0].endsWith("/r/retry") && c[1]?.method === "POST",
        ),
      ).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });
  it("surfaces a backend conflict message", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ detail: "Run already completed" }), {
          status: 409,
        }),
    );
    await expect(request("/runs/r/retry", "POST")).rejects.toThrow(
      "Run already completed",
    );
  });
});
