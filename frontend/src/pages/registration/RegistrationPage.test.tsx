import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { uz } from "../../i18n/uz";
import { RegistrationPage } from "./RegistrationPage";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}));
vi.mock("../../components/QrCode", () => ({ QrCode: () => null }));

const r = uz.registration;

const lookups = {
  categories: [{ id: 1, code: "GEN", name: "Umumiy yuk", special_handling: false }],
  shifts: [],
  docks: [],
};
const todayRow = {
  id: 7,
  queue_number: 3,
  awb_number: "176-00000010",
  consignee_name: "Eski MChJ",
  status: "REGISTERED",
  registered_at: "2026-11-04T05:00:00Z",
};

function ok<T>(data: T) {
  return { data, response: { ok: true, status: 200 } };
}
function fail(status: number, error: unknown) {
  return { data: undefined, error, response: { ok: false, status } };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockImplementation((url: string) =>
    Promise.resolve(
      url === "/api/lookups/"
        ? ok(lookups)
        : ok({ count: 1, next: null, previous: null, results: [todayRow] }),
    ),
  );
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RegistrationPage />
    </QueryClientProvider>,
  );
}

const verified = {
  verified: true,
  awb_number: "176-12345670",
  reason: "",
  permit: { id: 1, permit_number: "MOCK-17612345670", source: "MOCK", valid_until: null },
};

async function checkAwb(awb: string) {
  await userEvent.type(screen.getByLabelText(r.awb), awb);
  await userEvent.click(screen.getByRole("button", { name: r.check }));
}

async function fillValidForm() {
  const f = r.form;
  await userEvent.type(screen.getByLabelText(f.consigneeName), "Toshkent Savdo MChJ");
  await userEvent.clear(screen.getByLabelText(f.phone));
  await userEvent.type(screen.getByLabelText(f.phone), "+998901234567");
  await userEvent.type(screen.getByLabelText(f.pieces), "12");
  await userEvent.type(screen.getByLabelText(f.weight), "345.5");
  await userEvent.selectOptions(screen.getByLabelText(f.category), "GEN");
}

describe("RegistrationPage", () => {
  it("lists today's requests on the right", async () => {
    renderPage();
    expect(await screen.findByText("Eski MChJ")).toBeInTheDocument();
    expect(screen.getByText(uz.statuses.REGISTERED)).toBeInTheDocument();
  });

  it("asks for an AWB before checking", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: r.check }));
    expect(screen.getByText(r.awbRequired)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows a red banner with the reason and no form when the permit is rejected", async () => {
    post.mockResolvedValue(
      ok({
        verified: false,
        awb_number: "176-12345671",
        reason: "Ruxsatnoma topilmadi.",
        permit: null,
      }),
    );
    renderPage();
    await checkAwb("176-12345671");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(r.permitRejected);
    expect(banner).toHaveTextContent("Ruxsatnoma topilmadi.");
    expect(screen.queryByLabelText(r.form.consigneeName)).not.toBeInTheDocument();
  });

  it("shows a green banner and the form when the permit is verified", async () => {
    post.mockResolvedValue(ok(verified));
    renderPage();
    await checkAwb("176-12345670");
    expect(await screen.findByRole("status")).toHaveTextContent(r.permitOk);
    expect(screen.getByLabelText(r.form.consigneeName)).toBeInTheDocument();
  });

  it("hides the form again as soon as the AWB is edited", async () => {
    post.mockResolvedValue(ok(verified));
    renderPage();
    await checkAwb("176-12345670");
    await screen.findByLabelText(r.form.consigneeName);
    await userEvent.type(screen.getByLabelText(r.awb), "1");
    expect(screen.queryByLabelText(r.form.consigneeName)).not.toBeInTheDocument();
  });

  it("validates the form in Uzbek without calling the server", async () => {
    post.mockResolvedValue(ok(verified));
    renderPage();
    await checkAwb("176-12345670");
    await userEvent.click(await screen.findByRole("button", { name: r.form.submit }));
    expect(screen.getAllByText(r.validation.required).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(r.validation.phone)).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1); // only the permit check
  });

  it("creates the request, then shows the ticket window with the queue number", async () => {
    post.mockResolvedValueOnce(ok(verified)).mockResolvedValueOnce(
      ok({
        id: 9,
        queue_number: 4,
        ticket: {
          queue_number: 4,
          awb_number: "176-12345670",
          pieces_total: 12,
          weight_kg: "345.50",
          vehicle_plate: "",
          registered_at: "2026-11-04T05:00:00Z",
        },
      }),
    );
    renderPage();
    await checkAwb("176-12345670");
    await screen.findByLabelText(r.form.consigneeName);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: r.form.submit }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("queue-number")).toHaveTextContent("4");
    const body = post.mock.calls[1][1].body;
    expect(body).toMatchObject({
      awb_number: "176-12345670",
      consignee_name: "Toshkent Savdo MChJ",
      sms_phone: "+998901234567",
      pieces_total: 12,
      weight_kg: "345.5",
      category: "GEN",
    });
    // the form is closed and ready for the next customer
    await userEvent.click(within(dialog).getByRole("button", { name: r.ticket.close }));
    expect(screen.queryByLabelText(r.form.consigneeName)).not.toBeInTheDocument();
  });

  it("shows the server's reason when registration is refused", async () => {
    post
      .mockResolvedValueOnce(ok(verified))
      .mockResolvedValueOnce(
        fail(409, { detail: "Bu AWB bo‘yicha faol ariza allaqachon mavjud.", code: "duplicate" }),
      );
    renderPage();
    await checkAwb("176-12345670");
    await screen.findByLabelText(r.form.consigneeName);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: r.form.submit }));
    expect(await screen.findByText(/faol ariza allaqachon mavjud/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("puts server field errors under the matching input", async () => {
    post
      .mockResolvedValueOnce(ok(verified))
      .mockResolvedValueOnce(fail(400, { sms_phone: ["Telefon raqami noto‘g‘ri."] }));
    renderPage();
    await checkAwb("176-12345670");
    await screen.findByLabelText(r.form.consigneeName);
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: r.form.submit }));
    expect(await screen.findByText("Telefon raqami noto‘g‘ri.")).toBeInTheDocument();
  });
});
