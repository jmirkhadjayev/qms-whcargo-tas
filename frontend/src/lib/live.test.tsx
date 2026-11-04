import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, vi } from "vitest";

import { socketUrl, useLive, useLiveRefresh } from "./live";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  closed = false;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.();
  }
  push(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  drop(code = 1006) {
    this.onclose?.({ code });
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("socketUrl", () => {
  it("uses ws on http and wss on https", () => {
    expect(socketUrl("/ws/x/", { protocol: "http:", host: "localhost:5173" })).toBe(
      "ws://localhost:5173/ws/x/",
    );
    expect(socketUrl("/ws/x/", { protocol: "https:", host: "yuk.example" })).toBe(
      "wss://yuk.example/ws/x/",
    );
  });
});

describe("useLive", () => {
  it("connects, reports its state and hands over messages", () => {
    const received: unknown[] = [];
    const { result } = renderHook(() => useLive("/ws/warehouse/", (m) => received.push(m)));
    expect(result.current).toBe("connecting");
    expect(FakeSocket.instances[0].url).toBe("ws://localhost:3000/ws/warehouse/");

    act(() => FakeSocket.instances[0].open());
    expect(result.current).toBe("open");
    act(() => FakeSocket.instances[0].push({ event: "warehouse.task", task_id: 4 }));
    expect(received).toEqual([{ event: "warehouse.task", task_id: 4 }]);
  });

  it("ignores frames that are not JSON", () => {
    const received: unknown[] = [];
    renderHook(() => useLive("/ws/x/", (m) => received.push(m)));
    act(() => FakeSocket.instances[0].onmessage?.({ data: "not json" }));
    expect(received).toEqual([]);
  });

  it("reconnects with a growing delay after the connection drops", () => {
    const { result } = renderHook(() => useLive("/ws/x/", () => {}));
    act(() => FakeSocket.instances[0].drop());
    expect(result.current).toBe("closed");
    expect(FakeSocket.instances).toHaveLength(1);

    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => FakeSocket.instances[1].drop());
    act(() => vi.advanceTimersByTime(1_500));
    expect(FakeSocket.instances).toHaveLength(2); // second wait is 2 s, not 1.5 s
    act(() => vi.advanceTimersByTime(500));
    expect(FakeSocket.instances).toHaveLength(3);

    act(() => FakeSocket.instances[2].open()); // a good connection resets the delay
    act(() => FakeSocket.instances[2].drop());
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeSocket.instances).toHaveLength(4);
  });

  it.each([4403, 4404])("does not retry when the server refuses with %i", (code) => {
    renderHook(() => useLive("/ws/x/", () => {}));
    act(() => FakeSocket.instances[0].drop(code));
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("closes the socket and stops retrying on unmount", () => {
    const { unmount } = renderHook(() => useLive("/ws/x/", () => {}));
    const socket = FakeSocket.instances[0];
    unmount();
    expect(socket.closed).toBe(true);
    act(() => socket.drop());
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("stays disconnected when the path is null", () => {
    renderHook(() => useLive(null, () => {}));
    expect(FakeSocket.instances).toHaveLength(0);
  });
});

describe("useLiveRefresh", () => {
  it("refetches the given queries once for a burst of messages", () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    function Probe() {
      useLiveRefresh("/ws/x/", [["warehouse"], ["dispatcher"]]);
      return null;
    }
    render(<Probe />, { wrapper });

    act(() => {
      FakeSocket.instances[0].push({ event: "a" });
      FakeSocket.instances[0].push({ event: "b" });
      FakeSocket.instances[0].push({ event: "c" });
    });
    expect(spy).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(200));
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["warehouse"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["dispatcher"] });
  });
});
