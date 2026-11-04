import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { uz } from "../../i18n/uz";
import { WarehousePage } from "./WarehousePage";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}));
vi.mock("../../lib/live", () => ({ useLiveRefresh: () => "open" }));

const w = uz.warehouse;

function task(id: number, status: string, request: Record<string, unknown> = {}) {
  return {
    id,
    status,
    storage_location: "",
    assigned_to: null,
    created_at: "2026-11-04T05:00:00Z",
    started_at: null,
    ready_at: null,
    handed_over_at: null,
    request: {
      id: id + 100,
      queue_number: id,
      awb_number: `176-0000000${id}`,
      pieces_total: 12,
      weight_kg: "345.50",
      category: "GEN",
      category_name: "Umumiy yuk",
      special_handling: false,
      dock: null,
      status: "AWAITING_PREP",
      priority: 0,
      notes: "",
      ...request,
    },
  };
}

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } });
const fail = (status: number, error: unknown) => ({
  data: undefined,
  error,
  response: { ok: false, status },
});

let tasks: ReturnType<typeof task>[];

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  tasks = [
    task(1, "NEW", { notes: "Ehtiyotkorlik bilan", priority: 2 }),
    task(2, "IN_PROGRESS", { status: "PREP_STARTED", category: "DGR", special_handling: true }),
    task(3, "READY", { status: "AWAITING_DOCK" }),
    task(4, "READY", { status: "DOCK_ASSIGNED", dock: "D-02" }),
    task(5, "PROBLEM"),
  ];
  get.mockImplementation((url: string, options?: { params?: { query?: { code?: string } } }) => {
    if (url === "/api/warehouse/tasks/scan/") {
      const found = tasks.find((t) => t.request.awb_number === options?.params?.query?.code);
      return Promise.resolve(
        found ? ok(found) : fail(404, { detail: "Topshiriq topilmadi.", code: "task_not_found" }),
      );
    }
    return Promise.resolve(ok(tasks));
  });
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WarehousePage />
    </QueryClientProvider>,
  );
}

const tab = (name: keyof typeof w.tabs) =>
  within(screen.getByRole("navigation", { name: w.tabsLabel })).getByRole("button", {
    name: new RegExp(`^${w.tabs[name]}`),
  });

describe("WarehousePage", () => {
  it("shows tabs with counts and the cards of the selected tab", async () => {
    renderPage();
    expect(await screen.findByTestId("task-1")).toBeInTheDocument();
    expect(tab("NEW")).toHaveTextContent("(1)");
    expect(tab("READY")).toHaveTextContent("(2)");
    expect(screen.queryByTestId("task-2")).not.toBeInTheDocument();

    const card = screen.getByTestId("task-1");
    expect(within(card).getByText("176-00000001")).toBeInTheDocument();
    expect(within(card).getByText("Ehtiyotkorlik bilan")).toBeInTheDocument();
    expect(within(card).getByText(`${w.priority} 2`)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: w.start })).toBeInTheDocument();
  });

  it("marks special-handling cargo", async () => {
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.click(tab("IN_PROGRESS"));
    expect(within(screen.getByTestId("task-2")).getByTitle(w.special)).toHaveTextContent("DGR");
  });

  it("starts a task with the storage location", async () => {
    post.mockResolvedValue(ok(task(1, "IN_PROGRESS")));
    renderPage();
    const card = await screen.findByTestId("task-1");
    await userEvent.type(within(card).getByLabelText(w.fields.location), "A-12");
    await userEvent.click(within(card).getByRole("button", { name: w.start }));
    expect(post).toHaveBeenCalledWith(
      "/api/warehouse/tasks/{id}/start/",
      expect.objectContaining({ params: { path: { id: 1 } }, body: { storage_location: "A-12" } }),
    );
  });

  it("marks cargo ready", async () => {
    post.mockResolvedValue(ok(task(2, "READY")));
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.click(tab("IN_PROGRESS"));
    await userEvent.click(
      within(screen.getByTestId("task-2")).getByRole("button", { name: w.ready }),
    );
    expect(post).toHaveBeenCalledWith(
      "/api/warehouse/tasks/{id}/ready/",
      expect.objectContaining({ params: { path: { id: 2 } } }),
    );
  });

  it("allows hand-over only once a dock is assigned", async () => {
    post.mockResolvedValue(ok(task(4, "HANDED_OVER")));
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.click(tab("READY"));
    expect(
      within(screen.getByTestId("task-3")).getByRole("button", { name: w.handOver }),
    ).toBeDisabled();
    expect(within(screen.getByTestId("task-3")).getByText(w.needsDock)).toBeInTheDocument();

    const ready = within(screen.getByTestId("task-4")).getByRole("button", { name: w.handOver });
    expect(ready).toBeEnabled();
    await userEvent.click(ready);
    expect(post).toHaveBeenCalledWith(
      "/api/warehouse/tasks/{id}/handover/",
      expect.objectContaining({ params: { path: { id: 4 } } }),
    );
  });

  it("reports a problem; the description is required", async () => {
    post.mockResolvedValue(ok(task(1, "PROBLEM")));
    renderPage();
    const card = await screen.findByTestId("task-1");
    await userEvent.click(within(card).getByRole("button", { name: w.problem }));

    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: uz.common.send }));
    expect(within(dialog).getByText(w.problemDialog.descriptionRequired)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    await userEvent.selectOptions(within(dialog).getByLabelText(w.problemDialog.kind), "SHORTAGE");
    await userEvent.clear(within(dialog).getByLabelText(w.problemDialog.pieces));
    await userEvent.type(within(dialog).getByLabelText(w.problemDialog.pieces), "3");
    await userEvent.type(within(dialog).getByLabelText(w.problemDialog.description), "3 quti yo‘q");
    await userEvent.click(within(dialog).getByRole("button", { name: uz.common.send }));

    expect(post).toHaveBeenCalledWith(
      "/api/warehouse/tasks/{id}/problem/",
      expect.objectContaining({
        params: { path: { id: 1 } },
        body: { kind: "SHORTAGE", description: "3 quti yo‘q", pieces_affected: 3 },
      }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a task that has a problem without action buttons", async () => {
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.click(tab("PROBLEM"));
    const card = screen.getByTestId("task-5");
    expect(within(card).getByText(w.problemHeld)).toBeInTheDocument();
    expect(within(card).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the server's message when an action is refused", async () => {
    post.mockResolvedValue(
      fail(409, { detail: "Ariza to‘xtatib turilgan.", code: "request_suspended" }),
    );
    renderPage();
    const card = await screen.findByTestId("task-1");
    await userEvent.click(within(card).getByRole("button", { name: w.start }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ariza to‘xtatib turilgan.");
  });

  it("flags a suspended request and hides the work buttons", async () => {
    tasks = [task(1, "NEW", { status: "SUSPENDED" })];
    renderPage();
    const card = await screen.findByTestId("task-1");
    expect(within(card).getByText(w.suspended)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: w.start })).not.toBeInTheDocument();
  });

  it("finds a task by scanning, whichever tab is open", async () => {
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.type(screen.getByLabelText(w.scanLabel), "176-00000005{Enter}");
    const section = await screen.findByRole("region", { name: w.scanned });
    expect(within(section).getByTestId("task-5")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      "/api/warehouse/tasks/scan/",
      expect.objectContaining({ params: { query: { code: "176-00000005" } } }),
    );
    expect(screen.getByLabelText(w.scanLabel)).toHaveValue("");
  });

  it("says so when the scanned code matches nothing", async () => {
    renderPage();
    await screen.findByTestId("task-1");
    await userEvent.type(screen.getByLabelText(w.scanLabel), "999-99999999{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Topshiriq topilmadi.");
  });
});
