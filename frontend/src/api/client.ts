import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

// Django session + CSRF: send the token on every unsafe request.
const csrf: Middleware = {
  onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const token = readCookie("csrftoken");
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use(csrf);

/** Make sure the CSRF cookie exists before the first unsafe request (login). */
export async function ensureCsrf(): Promise<void> {
  if (!readCookie("csrftoken")) {
    await api.GET("/api/auth/csrf/");
  }
}
