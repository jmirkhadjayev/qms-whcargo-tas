import { uz } from "../i18n/uz";

/** An API error: a message for the banner, plus per-field messages when the server sent them. */
export class ApiProblem extends Error {
  constructor(
    message: string,
    readonly fields: Record<string, string[]> = {},
    readonly code?: string,
  ) {
    super(message);
  }
}

function toProblem(error: unknown): ApiProblem {
  if (error && typeof error === "object") {
    const body = error as Record<string, unknown>;
    if (typeof body.detail === "string") {
      return new ApiProblem(body.detail, {}, typeof body.code === "string" ? body.code : undefined);
    }
    const fields: Record<string, string[]> = {};
    for (const [key, value] of Object.entries(body)) {
      if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
        fields[key] = value as string[];
      }
    }
    if (Object.keys(fields).length > 0) {
      return new ApiProblem(Object.values(fields)[0][0], fields);
    }
  }
  return new ApiProblem(uz.app.networkError);
}

export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await request;
  } catch {
    throw new ApiProblem(uz.app.networkError);
  }
  if (!result.response.ok || result.data === undefined) throw toProblem(result.error);
  return result.data;
}
