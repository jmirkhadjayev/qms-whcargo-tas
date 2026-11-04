import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { uz } from "../../i18n/uz";
import { DispatcherPage } from "./DispatcherPage";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}));
vi.mock("../../lib/live", () => ({ useLiveRefresh: () => "open" }));

const d = uz.dispatcher;

const overview = {
  kpi: {
    registered_today: 14,
    in_preparation: 3,
    waiting_dock: 2,
    at_dock: 1,
    completed_today: 6,
    open_exceptions: 1,
    avg_wait_minutes: 42,
  },
  docks: [
    {
      id: 1,
      code: "D-01",
      name: "Dok 1",
      state: "BUSY",
      is_active: true,
      categories: ["GEN", "OVZ"],
      agent: "Dok Agenti",
      agent_ready: true,
      request: {
        id: 9,
        queue_number: 7,
        status: "CALLED",
        vehicle_plate: "01A123BC",
        category: "GEN",
      },
    },
    {
      id: 2,
      code: "D-02",
      name: "Dok 2",
      state: "FREE",
      is_active: true,
      categories: ["GEN"],
      request: null,
    },
    {
      id: 3,
      code: "D-03",
      name: "Dok 3",
      state: "MAINTENANCE",
      is_active: true,
      categories: ["DGR"],
      request: null,
    },
  ],
};

function row(queue_number: number, extra: Record<string, unknown> = {}) {
  return {
    id: queue_number * 10,
    queue_number,
    awb_number: `176-0000000${queue_number}`,
    consignee_name: `MChJ ${queue_number}`,
    category: "GEN",
    special_handling: false,
    status: "AWAITING_DOCK",
    priority: 0,
    dock: null,
    pieces_total: 5,
    vehicle_plate: "",
    wait_minutes: 25,
    task_status: "READY",
    free_docks: ["D-02", "D-04"],
    attempts: 0,
    recalls_left: 0,
    call_blockers: [],
    remaining_pieces: 0,
    suspended_from: null,
    ...extra,
  };
}

const exceptions = [
  {
    id: 71,
    request: 40,
    queue_number: 40,
    request_status: "AWAITING_CHECKPOINT",
    kind: "CHECKPOINT",
    description: "O‘rinlar soni mos kelmadi",
    reported_by: "NO‘P xodimi",
    resolved_at: null,
  },
];

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } });
const fail = (status: number, error: unknown) => ({
  data: undefined,
  error,
  response: { ok: false, status },
});

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockImplementation((url: string) =>
    Promise.resolve(
      url === "/api/dispatcher/overview/"
        ? ok(overview)
        : url === "/api/exceptions/"
          ? ok(exceptions)
          : ok([
              row(1, { priority: 3 }),
              row(2, { free_docks: [] }),
              row(3, { status: "AWAITING_PREP", free_docks: [], task_status: "IN_PROGRESS" }),
              row(4, { status: "CALLED", dock: "D-01", free_docks: [] }),
              row(5, {
                status: "DOCK_ASSIGNED",
                dock: "D-02",
                free_docks: [],
                call_blockers: ["agent_not_ready"],
              }),
              row(6, {
                status: "CALLED",
                dock: "D-03",
                free_docks: [],
                attempts: 2,
                recalls_left: 1,
              }),
              row(7, {
                status: "CALLED",
                dock: "D-04",
                free_docks: [],
                attempts: 3,
                recalls_left: 0,
              }),
              row(8, {
                status: "SUSPENDED",
                free_docks: [],
                suspended_from: "AWAITING_CHECKPOINT",
              }),
              row(9, { status: "EXIT_CONFIRMED", free_docks: [], remaining_pieces: 3 }),
              row(10, { status: "EXIT_CONFIRMED", free_docks: [], remaining_pieces: 0 }),
            ]),
    ),
  );
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DispatcherPage />
    </QueryClientProvider>,
  );
}

describe("DispatcherPage", () => {
  it("shows the KPI tiles", async () => {
    renderPage();
    // the tiles exist at once (with a dash); the numbers arrive with the data
    await waitFor(() => expect(screen.getByTestId("kpi-registered_today")).toHaveTextContent("14"));
    expect(screen.getByTestId("kpi-in_preparation")).toHaveTextContent("3");
    expect(screen.getByTestId("kpi-open_exceptions")).toHaveTextContent("1");
    expect(screen.getByTestId("kpi-avg_wait_minutes").textContent).toBe(`42${uz.common.minutes}`); // spacing is CSS
  });

  it("shows every dock with its state, ticket and categories", async () => {
    renderPage();
    const busy = await screen.findByTestId("dock-D-01");
    expect(within(busy).getByText(d.dockState.BUSY)).toBeInTheDocument();
    expect(within(busy).getByText(/№ 7/)).toBeInTheDocument();
    expect(within(busy).getByText("01A123BC")).toBeInTheDocument();
    expect(within(busy).getByText("OVZ")).toBeInTheDocument();
    expect(within(screen.getByTestId("dock-D-02")).getByText(d.dockState.FREE)).toBeInTheDocument();
    expect(
      within(screen.getByTestId("dock-D-03")).getByText(d.dockState.MAINTENANCE),
    ).toBeInTheDocument();
  });

  it("lists the queue and offers only the free docks that fit", async () => {
    renderPage();
    expect(await screen.findByTestId("row-1")).toBeInTheDocument();
    const options = within(screen.getByLabelText(`${d.chooseDock} № 1`)).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([d.chooseDock, "D-02", "D-04"]);
    expect(within(screen.getByTestId("row-2")).getByText(d.noFreeDock)).toBeInTheDocument();
    expect(within(screen.getByTestId("row-4")).getByText("D-01")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("row-3")).getByText(
        new RegExp(uz.warehouse.taskStatus.IN_PROGRESS),
      ),
    ).toBeInTheDocument();
  });

  it("assigns the chosen dock", async () => {
    post.mockResolvedValue(ok({}));
    renderPage();
    const rowEl = await screen.findByTestId("row-1");
    const assign = within(rowEl).getByRole("button", { name: d.assign });
    expect(assign).toBeDisabled(); // nothing chosen yet
    await userEvent.selectOptions(within(rowEl).getByLabelText(`${d.chooseDock} № 1`), "D-02");
    await userEvent.click(assign);
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/assign-dock/",
      expect.objectContaining({ params: { path: { id: 10 } }, body: { dock: "D-02" } }),
    );
  });

  it("shows the server's reason when a dock cannot be assigned", async () => {
    post.mockResolvedValue(fail(409, { detail: "Dok band.", code: "dock_busy" }));
    renderPage();
    const rowEl = await screen.findByTestId("row-1");
    await userEvent.selectOptions(within(rowEl).getByLabelText(`${d.chooseDock} № 1`), "D-02");
    await userEvent.click(within(rowEl).getByRole("button", { name: d.assign }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Dok band.");
  });

  it("raises and lowers the priority within 0..9", async () => {
    post.mockResolvedValue(ok({}));
    renderPage();
    await screen.findByTestId("row-1");
    await userEvent.click(screen.getByLabelText(`${d.priorityUp} № 1`));
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/priority/",
      expect.objectContaining({ params: { path: { id: 10 } }, body: { priority: 4 } }),
    );
    await userEvent.click(screen.getByLabelText(`${d.priorityDown} № 1`));
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/priority/",
      expect.objectContaining({ body: { priority: 2 } }),
    );
    expect(screen.getByLabelText(`${d.priorityDown} № 2`)).toBeDisabled(); // already 0
  });

  it("toggles maintenance, except for a busy dock", async () => {
    post.mockResolvedValue(ok({}));
    renderPage();
    const free = await screen.findByTestId("dock-D-02");
    await userEvent.click(within(free).getByRole("button", { name: d.toMaintenance }));
    expect(post).toHaveBeenLastCalledWith(
      "/api/dispatcher/docks/{code}/maintenance/",
      expect.objectContaining({ params: { path: { code: "D-02" } }, body: { maintenance: true } }),
    );
    await userEvent.click(
      within(screen.getByTestId("dock-D-03")).getByRole("button", { name: d.fromMaintenance }),
    );
    expect(post).toHaveBeenLastCalledWith(
      "/api/dispatcher/docks/{code}/maintenance/",
      expect.objectContaining({ params: { path: { code: "D-03" } }, body: { maintenance: false } }),
    );
    expect(
      within(screen.getByTestId("dock-D-01")).getByRole("button", { name: d.toMaintenance }),
    ).toBeDisabled();
  });

  it("shows who works at a dock", async () => {
    renderPage();
    const busy = await screen.findByTestId("dock-D-01");
    expect(within(busy).getByText("Dok Agenti")).toBeInTheDocument();
    expect(within(screen.getByTestId("dock-D-02")).getByText(d.noAgent)).toBeInTheDocument();
  });

  it("shows what a request with a dock is still waiting for, and lets the supervisor call by hand", async () => {
    post.mockResolvedValue(ok({}));
    renderPage();
    const rowEl = await screen.findByTestId("row-5");
    expect(within(rowEl).getByText(uz.callBlockers.agent_not_ready)).toBeInTheDocument();
    await userEvent.click(within(rowEl).getByRole("button", { name: d.call }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/call/",
      expect.objectContaining({ params: { path: { id: 50 } } }),
    );
  });

  it("calls again, as long as repeat calls are left", async () => {
    post.mockResolvedValue(ok({}));
    renderPage();
    const rowEl = await screen.findByTestId("row-6");
    expect(within(rowEl).getByText(`${d.callAttempt} 2`)).toBeInTheDocument();
    await userEvent.click(within(rowEl).getByRole("button", { name: d.recall }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/recall/",
      expect.objectContaining({ params: { path: { id: 60 } } }),
    );
    expect(
      within(screen.getByTestId("row-7")).getByRole("button", { name: d.recall }),
    ).toBeDisabled();
  });

  describe("decisions waiting for the supervisor", () => {
    it("lists the open problem with what was found and who reported it", async () => {
      renderPage();
      const item = await screen.findByTestId("exception-71");
      expect(within(item).getByText("№ 40")).toBeInTheDocument();
      expect(within(item).getByText(d.attention.kinds.CHECKPOINT)).toBeInTheDocument();
      expect(within(item).getByText("O‘rinlar soni mos kelmadi")).toBeInTheDocument();
      expect(within(item).getByText(/NO‘P xodimi/)).toBeInTheDocument();
    });

    it("resolves a problem only with a written decision", async () => {
      post.mockResolvedValue(ok({}));
      renderPage();
      const item = await screen.findByTestId("exception-71");
      await userEvent.click(within(item).getByRole("button", { name: d.attention.resolve }));
      expect(within(item).getByText(d.attention.reasonRequired)).toBeInTheDocument();
      expect(post).not.toHaveBeenCalled();

      await userEvent.type(
        within(item).getByLabelText(d.attention.resolution),
        "Hujjatlar tekshirildi",
      );
      await userEvent.click(within(item).getByRole("button", { name: d.attention.resolve }));
      expect(post).toHaveBeenCalledWith(
        "/api/exceptions/{id}/resolve/",
        expect.objectContaining({
          params: { path: { id: 71 } },
          body: { resolution: "Hujjatlar tekshirildi" },
        }),
      );
    });

    it("resumes a suspended request with a reason", async () => {
      post.mockResolvedValue(ok({}));
      renderPage();
      const item = await screen.findByTestId("suspended-8");
      expect(within(item).getByText(uz.statuses.AWAITING_CHECKPOINT)).toBeInTheDocument();
      await userEvent.type(
        within(item).getByLabelText(d.attention.resumeReason),
        "Tafovut hal qilindi",
      );
      await userEvent.click(within(item).getByRole("button", { name: d.attention.resume }));
      expect(post).toHaveBeenCalledWith(
        "/api/requests/{id}/resume/",
        expect.objectContaining({
          params: { path: { id: 80 } },
          body: { reason: "Tafovut hal qilindi" },
        }),
      );
    });

    it("decides about a remainder: prepare it again, or close with a documented reason", async () => {
      post.mockResolvedValue(ok({}));
      renderPage();
      const item = await screen.findByTestId("decision-9");
      expect(within(item).getByText("3")).toBeInTheDocument();
      expect(screen.queryByTestId("decision-10")).not.toBeInTheDocument(); // nothing left over

      await userEvent.click(within(item).getByRole("button", { name: d.attention.reprep }));
      expect(post).toHaveBeenLastCalledWith(
        "/api/requests/{id}/transition/",
        expect.objectContaining({
          params: { path: { id: 90 } },
          body: { to_status: "AWAITING_PREP", reason: undefined },
        }),
      );

      await userEvent.click(within(item).getByRole("button", { name: d.attention.close }));
      expect(within(item).getByText(d.attention.reasonRequired)).toBeInTheDocument();
      await userEvent.type(within(item).getByLabelText(d.attention.closeReason), "Mijoz rad etdi");
      await userEvent.click(within(item).getByRole("button", { name: d.attention.close }));
      expect(post).toHaveBeenLastCalledWith(
        "/api/requests/{id}/transition/",
        expect.objectContaining({ body: { to_status: "CLOSED", reason: "Mijoz rad etdi" } }),
      );
    });
  });
});
