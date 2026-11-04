import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { uz } from "../../i18n/uz";
import { CheckpointPage } from "./CheckpointPage";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}));
const liveRefresh = vi.fn(() => "open");
vi.mock("../../lib/live", () => ({
  useLiveRefresh: (...args: unknown[]) => liveRefresh(...(args as [])),
}));

const c = uz.checkpoint;

const overview = {
  waiting: [
    {
      id: 5,
      queue_number: 5,
      vehicle_plate: "01A123BC",
      pieces_released: 7,
      pieces_total: 10,
      is_partial: true,
    },
    {
      id: 6,
      queue_number: 6,
      vehicle_plate: "",
      pieces_released: 4,
      pieces_total: 4,
      is_partial: false,
    },
  ],
  recent: [
    {
      queue_number: 3,
      result: "APPROVED",
      scanned_at: "2026-11-04T05:00:00Z",
      officer: "NO‘P xodimi",
    },
    { queue_number: 4, result: "HELD", scanned_at: "2026-11-04T05:10:00Z", officer: "NO‘P xodimi" },
  ],
};

function summary(extra: Record<string, unknown> = {}) {
  return {
    id: 5,
    queue_number: 5,
    awb_number: "176-00000005",
    consignee_name: "Sinov MChJ",
    category: "GEN",
    special_handling: false,
    vehicle_plate: "01A123BC",
    pieces_total: 10,
    pieces_released: 10,
    pieces_remaining: 0,
    weight_kg: "100.00",
    status: "AWAITING_CHECKPOINT",
    dock: "D-01",
    can_confirm: true,
    blocked_reason: "",
    open_problems: [],
    ...extra,
  };
}

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } });
const fail = (status: number, error: unknown) => ({
  data: undefined,
  error,
  response: { ok: false, status },
});

let scanResult: unknown;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  liveRefresh.mockClear();
  scanResult = ok(summary());
  get.mockImplementation((url: string) =>
    Promise.resolve(url === "/api/checkpoint/overview/" ? ok(overview) : scanResult),
  );
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CheckpointPage />
    </QueryClientProvider>,
  );
}

async function scan(code = "5") {
  await userEvent.type(await screen.findByLabelText(c.scanLabel), `${code}{Enter}`);
  return screen.findByTestId("check-number");
}

async function tickAll() {
  for (const label of Object.values(c.checks)) {
    await userEvent.click(screen.getByLabelText(label));
  }
}

describe("CheckpointPage", () => {
  it("lists who is waiting and who has just passed, and listens for updates", async () => {
    renderPage();
    expect(await screen.findByText(/Qisman 7\/10/)).toBeInTheDocument();
    expect(screen.getAllByText(c.result.APPROVED)).toHaveLength(1);
    expect(screen.getByText(c.result.HELD)).toBeInTheDocument();
    expect(liveRefresh).toHaveBeenCalledWith("/ws/checkpoint/", expect.anything());
  });

  it("opens a waiting vehicle with one tap", async () => {
    renderPage();
    await userEvent.click(await screen.findByText("01A123BC"));
    expect(await screen.findByTestId("check-number")).toHaveTextContent("5");
    expect(get).toHaveBeenCalledWith(
      "/api/checkpoint/scan/",
      expect.objectContaining({ params: { query: { code: "5" } } }),
    );
  });

  it("shows what the officer compares with the vehicle", async () => {
    renderPage();
    await scan();
    expect(screen.getByTestId("registered-plate")).toHaveTextContent("01A123BC");
    expect(screen.getByTestId("pieces")).toHaveTextContent("10 / 10");
    expect(screen.getByText("Sinov MChJ")).toBeInTheDocument();
  });

  it("makes the officer tick every check before the exit can be confirmed", async () => {
    renderPage();
    await scan();
    const confirm = screen.getByRole("button", { name: c.confirm });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText(c.checks.ticket));
    await userEvent.click(screen.getByLabelText(c.checks.plate));
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText(c.checks.pieces));
    await userEvent.click(screen.getByLabelText(c.checks.docs));
    expect(confirm).toBeEnabled();
  });

  it("confirms the exit with the observed plate", async () => {
    post.mockResolvedValue(ok(summary({ status: "CLOSED", can_confirm: false })));
    renderPage();
    await scan();
    await tickAll();
    await userEvent.type(screen.getByLabelText(c.plateObserved), "01a123bc");
    await userEvent.click(screen.getByRole("button", { name: c.confirm }));
    expect(post).toHaveBeenCalledWith(
      "/api/checkpoint/{id}/confirm/",
      expect.objectContaining({
        params: { path: { id: 5 } },
        body: { plate_observed: "01a123bc" },
      }),
    );
    expect(await screen.findByText(c.confirmed)).toBeInTheDocument();
    expect(screen.queryByTestId("check-number")).not.toBeInTheDocument();
  });

  it("points out a remainder", async () => {
    scanResult = ok(summary({ pieces_released: 7, pieces_remaining: 3 }));
    renderPage();
    await scan();
    expect(screen.getByText(c.remainder)).toBeInTheDocument();
    expect(screen.getByTestId("pieces")).toHaveTextContent("7 / 10");
  });

  it("shows the open problems of the request", async () => {
    scanResult = ok(summary({ open_problems: [{ kind: "DAMAGE", description: "Quti ezilgan" }] }));
    renderPage();
    await scan();
    expect(screen.getByText("Quti ezilgan")).toBeInTheDocument();
  });

  it("refuses to confirm a vehicle that is not waiting, and says why", async () => {
    scanResult = ok(
      summary({
        status: "RELEASE_STARTED",
        can_confirm: false,
        blocked_reason: "Yuk berish hali tugamagan.",
      }),
    );
    renderPage();
    await scan();
    expect(screen.getByRole("alert")).toHaveTextContent("Yuk berish hali tugamagan.");
    expect(screen.queryByRole("button", { name: c.confirm })).not.toBeInTheDocument();
  });

  it("tells the officer to record a discrepancy when the plate differs", async () => {
    post.mockResolvedValue(
      fail(409, {
        detail: "Davlat raqami arizadagi bilan mos kelmaydi. Tafovutni qayd eting.",
        code: "plate_mismatch",
      }),
    );
    renderPage();
    await scan();
    await tickAll();
    await userEvent.type(screen.getByLabelText(c.plateObserved), "01B999ZZ");
    await userEvent.click(screen.getByRole("button", { name: c.confirm }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tafovutni qayd eting");
    expect(screen.getByTestId("check-number")).toBeInTheDocument(); // still open: record it
  });

  it("holds the exit on a discrepancy: a description is required", async () => {
    post.mockResolvedValue(ok(summary({ status: "SUSPENDED", can_confirm: false })));
    renderPage();
    await scan();
    await userEvent.type(screen.getByLabelText(c.plateObserved), "01B999ZZ");
    await userEvent.click(screen.getByRole("button", { name: c.hold }));

    const dialog = screen.getByRole("dialog", { name: c.holdTitle });
    await userEvent.click(within(dialog).getByRole("button", { name: c.holdSubmit }));
    expect(within(dialog).getByText(c.holdRequired)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    await userEvent.type(within(dialog).getByLabelText(c.holdDescription), "Yuk soni mos kelmadi");
    await userEvent.click(within(dialog).getByRole("button", { name: c.holdSubmit }));
    expect(post).toHaveBeenCalledWith(
      "/api/checkpoint/{id}/hold/",
      expect.objectContaining({
        params: { path: { id: 5 } },
        body: { description: "Yuk soni mos kelmadi", plate_observed: "01B999ZZ" },
      }),
    );
    expect(await screen.findByText(c.held)).toBeInTheDocument();
  });

  it("does not need the checklist to report a discrepancy", async () => {
    renderPage();
    await scan();
    expect(screen.getByRole("button", { name: c.hold })).toBeEnabled();
  });

  it("says so when the ticket is unknown", async () => {
    scanResult = fail(404, { detail: "Bunday talon topilmadi.", code: "request_not_found" });
    renderPage();
    await userEvent.type(await screen.findByLabelText(c.scanLabel), "999{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Bunday talon topilmadi.");
  });
});
