import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, vi } from "vitest";

import { App } from "./App";
import { uz } from "./i18n/uz";

const get = vi.fn();
const post = vi.fn();

vi.mock("./pages/dispatcher/DispatcherPage", () => ({
  DispatcherPage: () => <h1>{uz.sections.dispatcher}</h1>,
}));
vi.mock("./pages/checkpoint/CheckpointPage", () => ({
  CheckpointPage: () => <h1>{uz.sections.checkpoint}</h1>,
}));
vi.mock("./pages/dock/DockPage", () => ({
  DockPage: () => <h1>{uz.sections.dock}</h1>,
}));
vi.mock("./pages/warehouse/WarehousePage", () => ({
  WarehousePage: () => <h1>{uz.sections.warehouse}</h1>,
}));

vi.mock("./api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
  ensureCsrf: async () => {},
}));

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const user = (role: string) => ({
  data: { id: 1, username: "u", full_name: "Test Foydalanuvchi", role },
  response: { status: 200, ok: true },
});

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("App", () => {
  it("sends anonymous visitors to the login page", async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 403, ok: false } });
    renderAt("/dock");
    expect(await screen.findByRole("heading", { name: uz.login.title })).toBeInTheDocument();
  });

  it("validates empty login form in Uzbek", async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 403, ok: false } });
    renderAt("/login");
    await userEvent.click(await screen.findByRole("button", { name: uz.login.submit }));
    expect(screen.getAllByText(uz.login.required)).toHaveLength(2);
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the server error on wrong credentials", async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 403, ok: false } });
    post.mockResolvedValue({
      data: undefined,
      error: { detail: uz.login.failed },
      response: { status: 400, ok: false },
    });
    renderAt("/login");
    await userEvent.type(await screen.findByLabelText(uz.login.username), "agent");
    await userEvent.type(screen.getByLabelText(uz.login.password), "bad");
    await userEvent.click(screen.getByRole("button", { name: uz.login.submit }));
    expect(await screen.findByRole("alert")).toHaveTextContent(uz.login.failed);
  });

  it("lands a logged-in SUPERVISOR on the dispatcher section", async () => {
    get.mockResolvedValue(user("SUPERVISOR"));
    renderAt("/login");
    expect(
      await screen.findByRole("heading", { name: uz.sections.dispatcher }),
    ).toBeInTheDocument();
  });

  it("redirects a role away from a section it may not open", async () => {
    get.mockResolvedValue(user("WAREHOUSE"));
    renderAt("/admin");
    expect(await screen.findByRole("heading", { name: uz.sections.warehouse })).toBeInTheDocument();
  });
});
