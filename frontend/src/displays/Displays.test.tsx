import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, vi } from "vitest";

import { uz } from "../i18n/uz";
import { HallDisplay } from "./hall/HallDisplay";
import { LedDisplay } from "./led/LedDisplay";
import { screenToken } from "./useScreenData";

const get = vi.fn();
vi.mock("../api/client", () => ({ api: { GET: (...a: unknown[]) => get(...a) } }));
const liveRefresh = vi.fn(() => "open");
vi.mock("../lib/live", () => ({
  useLiveRefresh: (...args: unknown[]) => liveRefresh(...(args as [])),
}));

const t = uz.display;
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } });
const forbidden = () => ({ data: undefined, response: { ok: false, status: 403 } });

beforeEach(() => {
  get.mockReset();
  liveRefresh.mockClear();
  window.history.replaceState(null, "", "/");
});

function renderAt(element: React.ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={element} />
          <Route path="/display/led/:code" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("screenToken", () => {
  it("reads the token from the address", () => {
    expect(screenToken("?token=abc_123")).toBe("abc_123");
    expect(screenToken("")).toBeNull();
  });
});

describe("HallDisplay", () => {
  const board = {
    called: [
      { queue_number: 17, dock: "D-03", vehicle_plate: "01A123BC", recall: false },
      { queue_number: 9, dock: "D-01", vehicle_plate: "", recall: true },
    ],
    preparing: [{ queue_number: 18 }, { queue_number: 19 }],
  };

  it("lists who is called to which dock, and who is being prepared", async () => {
    get.mockResolvedValue(ok(board));
    renderAt(<HallDisplay />);
    const rows = await screen.findAllByTestId("called-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("17")).toBeInTheDocument();
    expect(within(rows[0]).getByText("D-03")).toBeInTheDocument();
    expect(within(rows[0]).getByText("01A123BC")).toBeInTheDocument();
    expect(within(rows[1]).getByText(t.recall)).toBeInTheDocument(); // a repeat call is marked
    expect(screen.getAllByTestId("preparing-row").map((r) => r.textContent)).toEqual(["18", "19"]);
  });

  it("says so when nobody is called", async () => {
    get.mockResolvedValue(ok({ called: [], preparing: [] }));
    renderAt(<HallDisplay />);
    expect(await screen.findByText(t.nobody)).toBeInTheDocument();
  });

  it("sends the screen token from the address, and uses it for the live channel", async () => {
    window.history.replaceState(null, "", "/display/hall?token=sekret");
    get.mockResolvedValue(ok(board));
    renderAt(<HallDisplay />);
    await screen.findAllByTestId("called-row");
    expect(get).toHaveBeenCalledWith(
      "/api/display/hall/",
      expect.objectContaining({ params: { query: { token: "sekret" } } }),
    );
    expect(liveRefresh).toHaveBeenCalledWith("/ws/display/hall/?token=sekret", expect.anything());
  });

  it("works without a token (allowed network)", async () => {
    get.mockResolvedValue(ok(board));
    renderAt(<HallDisplay />);
    await screen.findAllByTestId("called-row");
    expect(get).toHaveBeenCalledWith(
      "/api/display/hall/",
      expect.objectContaining({ params: { query: { token: undefined } } }),
    );
    expect(liveRefresh).toHaveBeenCalledWith("/ws/display/hall/", expect.anything());
  });

  it("tells a client without access, instead of an empty board", async () => {
    get.mockResolvedValue(forbidden());
    renderAt(<HallDisplay />);
    expect(await screen.findByText(t.forbidden)).toBeInTheDocument();
  });

  it("shows when the connection to the server is lost", async () => {
    get.mockRejectedValue(new Error("network"));
    renderAt(<HallDisplay />);
    expect(await screen.findByText(t.offline)).toBeInTheDocument();
  });
});

describe("LedDisplay", () => {
  const led = (current: unknown, state = "BUSY") => ok({ dock: "D-03", state, current });

  it("shows the called customer: ticket number and plate, big", async () => {
    get.mockResolvedValue(
      led({ queue_number: 17, vehicle_plate: "01A123BC", phase: "CALLING", recall: false }),
    );
    renderAt(<LedDisplay />, "/display/led/d-03");
    expect(await screen.findByTestId("led-number")).toHaveTextContent("17");
    expect(screen.getByTestId("led-plate")).toHaveTextContent("01A123BC");
    expect(screen.getByTestId("led-dock")).toHaveTextContent("D-03");
    expect(screen.getByText(t.ledCalling)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      "/api/display/led/{code}/",
      expect.objectContaining({ params: { path: { code: "D-03" }, query: { token: undefined } } }),
    );
  });

  it("shows that service is under way", async () => {
    get.mockResolvedValue(
      led({ queue_number: 17, vehicle_plate: "", phase: "SERVING", recall: false }),
    );
    renderAt(<LedDisplay />, "/display/led/D-03");
    expect(await screen.findByText(t.ledServing)).toBeInTheDocument();
    expect(screen.getByTestId("led-plate")).toHaveTextContent("—");
  });

  it("shows an idle dock", async () => {
    get.mockResolvedValue(led(null, "FREE"));
    renderAt(<LedDisplay />, "/display/led/D-03");
    expect((await screen.findAllByText(t.ledIdle)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("led-number")).not.toBeInTheDocument();
  });

  it("shows a dock in maintenance even if a request is attached", async () => {
    get.mockResolvedValue(
      led({ queue_number: 17, vehicle_plate: "", phase: "CALLING", recall: false }, "MAINTENANCE"),
    );
    renderAt(<LedDisplay />, "/display/led/D-03");
    expect((await screen.findAllByText(t.ledMaintenance)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("led-number")).not.toBeInTheDocument();
  });

  it("tells a client without access", async () => {
    get.mockResolvedValue(forbidden());
    renderAt(<LedDisplay />, "/display/led/D-03");
    expect(await screen.findByText(t.forbidden)).toBeInTheDocument();
  });

  it("listens on the channel of its own dock", async () => {
    get.mockResolvedValue(led(null, "FREE"));
    renderAt(<LedDisplay />, "/display/led/d-03");
    await screen.findAllByText(t.ledIdle);
    expect(liveRefresh).toHaveBeenCalledWith("/ws/display/led/D-03/", expect.anything());
  });
});
