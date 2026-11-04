import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { uz } from "../../i18n/uz";
import { DockPage } from "./DockPage";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}));
const liveRefresh = vi.fn(() => "open");
vi.mock("../../lib/live", () => ({
  useLiveRefresh: (...args: unknown[]) => liveRefresh(...(args as [])),
}));

const d = uz.dock;
const soon = () => new Date(Date.now() + 7 * 60_000).toISOString();

const SIGNED_OUT = {
  dock: null,
  current: null,
  next: [],
  available_docks: [
    { code: "D-01", name: "Dok 1", categories: ["GEN", "OVZ"] },
    { code: "D-02", name: "Dok 2", categories: ["GEN"] },
  ],
};

function current(extra: Record<string, unknown> = {}) {
  return {
    id: 55,
    queue_number: 21,
    awb_number: "176-00000021",
    consignee_name: "Sinov MChJ",
    representative_name: "Aliyev Vali",
    category: "GEN",
    special_handling: false,
    pieces_total: 12,
    weight_kg: "345.50",
    vehicle_plate: "01A123BC",
    notes: "Ehtiyotkorlik bilan",
    status: "CALLED",
    attempt_no: 1,
    recalls_left: 2,
    timeout_at: soon(),
    blockers: [],
    pieces_released: 0,
    pieces_remaining: 12,
    operation_pieces: 0,
    history: [
      { from_status: "DOCK_ASSIGNED", to_status: "CALLED", changed_at: "2026-11-04T09:50:00Z" },
    ],
    ...extra,
  };
}

function signedIn(cur: unknown) {
  return {
    dock: { code: "D-03", name: "Dok 3", state: "BUSY", ready_since: "2026-11-04T04:00:00Z" },
    current: cur,
    next: [{ queue_number: 22, category: "GEN", vehicle_plate: "", wait_minutes: 14 }],
    available_docks: [],
  };
}

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } });
const fail = (status: number, error: unknown) => ({
  data: undefined,
  error,
  response: { ok: false, status },
});

let screenData: unknown;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  liveRefresh.mockClear();
  screenData = SIGNED_OUT;
  get.mockImplementation((url: string, options?: { params?: { query?: { code?: string } } }) => {
    if (url === "/api/dock/scan/") {
      const code = options?.params?.query?.code;
      if (code === "21") return Promise.resolve(ok({ id: 55, queue_number: 21, status: "CALLED" }));
      if (code === "30")
        return Promise.resolve(ok({ id: 60, queue_number: 30, status: "ARRIVED" }));
      return Promise.resolve(fail(404, { detail: "Talon topilmadi.", code: "scan_not_found" }));
    }
    return Promise.resolve(ok(screenData));
  });
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DockPage />
    </QueryClientProvider>,
  );
}

describe("DockPage before signing in", () => {
  it("offers the free docks and signs in to the chosen one", async () => {
    post.mockResolvedValue(ok(signedIn(null)));
    renderPage();
    expect(await screen.findByRole("heading", { name: d.pickTitle })).toBeInTheDocument();
    expect(liveRefresh).toHaveBeenLastCalledWith(null, expect.anything()); // no dock, no channel
    await userEvent.click(screen.getByRole("button", { name: /D-02/ }));
    expect(post).toHaveBeenCalledWith("/api/dock/checkin/", { body: { dock: "D-02" } });
  });

  it("says so when no dock is free", async () => {
    screenData = { ...SIGNED_OUT, available_docks: [] };
    renderPage();
    expect(await screen.findByText(d.noFreeDocks)).toBeInTheDocument();
  });

  it("shows why signing in was refused", async () => {
    post.mockResolvedValue(
      fail(409, { detail: "Bu dokda boshqa xodim ishlayapti.", code: "dock_has_agent" }),
    );
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /D-01/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu dokda boshqa xodim ishlayapti.");
  });
});

describe("DockPage at a dock", () => {
  it("shows the dock, that the agent is ready, and the next customers", async () => {
    screenData = signedIn(null);
    renderPage();
    expect(
      await screen.findByRole("heading", { name: new RegExp(`${d.title} D-03`) }),
    ).toHaveTextContent(d.ready);
    expect(liveRefresh).toHaveBeenLastCalledWith("/ws/dock/D-03/", expect.anything());
    expect(screen.getByText(d.waitingTitle)).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
  });

  it("shows the called customer with a countdown and the repeat-call allowance", async () => {
    screenData = signedIn(current());
    renderPage();
    const section = await screen.findByRole("region", { name: d.called });
    expect(within(section).getByTestId("current-number")).toHaveTextContent("21");
    expect(within(section).getByTestId("countdown")).toHaveTextContent(/0[67]:\d\d/);
    expect(within(section).getByText(/Chaqiruv 1/)).toHaveTextContent(`${d.recallsLeft}: 2`);
    expect(within(section).getByText("01A123BC")).toBeInTheDocument();
    expect(within(section).getByText("Sinov MChJ")).toBeInTheDocument();
  });

  it("confirms the arrival", async () => {
    post.mockResolvedValue(ok({}));
    screenData = signedIn(current());
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: d.arrive }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/arrive/",
      expect.objectContaining({ params: { path: { id: 55 } } }),
    );
  });

  it("calls again, until no recalls are left", async () => {
    post.mockResolvedValue(ok({}));
    screenData = signedIn(current({ recalls_left: 1 }));
    const view = renderPage();
    await userEvent.click(await screen.findByRole("button", { name: d.recall }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/recall/",
      expect.objectContaining({ params: { path: { id: 55 } } }),
    );
    view.unmount();

    screenData = signedIn(current({ recalls_left: 0 }));
    renderPage();
    expect(await screen.findByRole("button", { name: d.recall })).toBeDisabled();
  });

  it("explains what a waiting call is missing", async () => {
    screenData = signedIn(
      current({ status: "DOCK_ASSIGNED", timeout_at: null, blockers: ["cargo_not_ready"] }),
    );
    renderPage();
    expect(await screen.findByText(d.waitingForReady)).toBeInTheDocument();
    expect(screen.getByText(uz.callBlockers.cargo_not_ready)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: d.arrive })).not.toBeInTheDocument();
  });

  it("scanning the ticket of the called customer records the arrival", async () => {
    post.mockResolvedValue(ok({}));
    screenData = signedIn(current());
    renderPage();
    await userEvent.type(await screen.findByLabelText(d.scanLabel), "21{Enter}");
    expect(await screen.findByText(d.scanAccepted)).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/arrive/",
      expect.objectContaining({ params: { path: { id: 55 } } }),
    );
  });

  it("does not record an arrival for a ticket that is not being called", async () => {
    screenData = signedIn(current());
    renderPage();
    await userEvent.type(await screen.findByLabelText(d.scanLabel), "30{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(d.scanNotCalled);
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the server's message for an unknown ticket", async () => {
    screenData = signedIn(current());
    renderPage();
    await userEvent.type(await screen.findByLabelText(d.scanLabel), "999{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Talon topilmadi.");
  });

  it("signs out, and shows why it is refused while a customer is at the dock", async () => {
    post.mockResolvedValue(
      fail(409, { detail: "Dokda mijoz bor — dokdan chiqib bo‘lmaydi.", code: "checkout_blocked" }),
    );
    screenData = signedIn(current());
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: d.checkOut }));
    expect(post).toHaveBeenCalledWith("/api/dock/checkout/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Dokda mijoz bor");
  });
});

describe("DockPage: releasing the cargo", () => {
  const r = d.release;

  it("starts the release once the customer has arrived", async () => {
    post.mockResolvedValue(ok({}));
    screenData = signedIn(current({ status: "ARRIVED", timeout_at: null }));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: r.start }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/release/start/",
      expect.objectContaining({ params: { path: { id: 55 } } }),
    );
  });

  function releasing(extra: Record<string, unknown> = {}) {
    return signedIn(
      current({
        status: "RELEASE_STARTED",
        timeout_at: null,
        pieces_released: 4,
        pieces_remaining: 8,
        operation_pieces: 4,
        ...extra,
      }),
    );
  }

  it("shows the count and what is left", async () => {
    screenData = releasing();
    renderPage();
    const panel = await screen.findByRole("region", { name: r.title });
    expect(within(panel).getByLabelText(r.thisRound)).toHaveValue("4");
    expect(within(panel).getByTestId("release-totals")).toHaveTextContent("4 / 12");
    expect(within(panel).getByTestId("release-totals")).toHaveTextContent(`${r.remaining}: 8`);
  });

  it("counts pieces up and down, never below zero or past the total", async () => {
    post.mockResolvedValue(ok({}));
    screenData = releasing();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: r.plus }));
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/release/progress/",
      expect.objectContaining({ params: { path: { id: 55 } }, body: { pieces_released: 5 } }),
    );
    await userEvent.click(screen.getByRole("button", { name: r.minus }));
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/release/progress/",
      expect.objectContaining({ body: { pieces_released: 3 } }),
    );
    await userEvent.click(screen.getByRole("button", { name: r.all }));
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/release/progress/",
      expect.objectContaining({ body: { pieces_released: 12 } }),
    );
  });

  it("accepts a typed number", async () => {
    post.mockResolvedValue(ok({}));
    screenData = releasing();
    renderPage();
    const input = await screen.findByLabelText(r.thisRound);
    await userEvent.clear(input);
    await userEvent.type(input, "7{Enter}");
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/release/progress/",
      expect.objectContaining({ body: { pieces_released: 7 } }),
    );
  });

  it("does not offer more than what is left to hand over", async () => {
    screenData = releasing({ pieces_released: 12, pieces_remaining: 0, operation_pieces: 12 });
    renderPage();
    expect(await screen.findByRole("button", { name: r.plus })).toBeDisabled();
    expect(screen.getByRole("button", { name: r.all })).toBeDisabled();
  });

  it("can finish only when every piece has been handed over", async () => {
    post.mockResolvedValue(ok({}));
    screenData = releasing();
    const view = renderPage();
    expect(await screen.findByRole("button", { name: r.finish })).toBeDisabled();
    expect(screen.getByRole("button", { name: r.partial })).toBeEnabled();
    view.unmount();

    screenData = releasing({ pieces_released: 12, pieces_remaining: 0, operation_pieces: 12 });
    renderPage();
    const finish = await screen.findByRole("button", { name: r.finish });
    expect(finish).toBeEnabled();
    expect(screen.getByRole("button", { name: r.partial })).toBeDisabled();
    await userEvent.click(finish);
    expect(post).toHaveBeenLastCalledWith(
      "/api/requests/{id}/release/finish/",
      expect.objectContaining({ params: { path: { id: 55 } } }),
    );
    expect(await screen.findByText(r.done)).toBeInTheDocument();
  });

  it("records a partial release: reason and comment are mandatory", async () => {
    post.mockResolvedValue(ok({}));
    screenData = releasing();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: r.partial }));

    const dialog = screen.getByRole("dialog", { name: r.partialDialog.title });
    expect(within(dialog).getByText("4 / 12")).toBeInTheDocument();
    expect(within(dialog).getByText("8")).toBeInTheDocument(); // not given

    await userEvent.click(within(dialog).getByRole("button", { name: r.partialDialog.submit }));
    expect(within(dialog).getByText(r.partialDialog.commentRequired)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    await userEvent.selectOptions(
      within(dialog).getByLabelText(r.partialDialog.reason),
      "SHORTAGE",
    );
    await userEvent.type(
      within(dialog).getByLabelText(r.partialDialog.comment),
      "Omborda 8 quti yo‘q",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: r.partialDialog.submit }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/release/partial/",
      expect.objectContaining({
        params: { path: { id: 55 } },
        body: { reason: "SHORTAGE", comment: "Omborda 8 quti yo‘q" },
      }),
    );
    expect(await screen.findByText(r.partialDone)).toBeInTheDocument();
  });

  it("reports a problem with the cargo", async () => {
    post.mockResolvedValue(ok({}));
    screenData = releasing();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: d.problem }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(
      within(dialog).getByLabelText(uz.warehouse.problemDialog.description),
      "Quti ezilgan",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: uz.common.send }));
    expect(post).toHaveBeenCalledWith(
      "/api/requests/{id}/problems/",
      expect.objectContaining({
        params: { path: { id: 55 } },
        body: { kind: "DAMAGE", description: "Quti ezilgan", pieces_affected: 0 },
      }),
    );
  });

  it("shows the server's reason when the release is refused", async () => {
    post.mockResolvedValue(
      fail(409, {
        detail: "Berilgan o‘rinlar soni jami o‘rinlardan oshib ketdi.",
        code: "release_exceeds",
      }),
    );
    screenData = releasing();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: r.plus }));
    expect(await screen.findByRole("alert")).toHaveTextContent("oshib ketdi");
  });
});
