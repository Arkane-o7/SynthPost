export const API_BASE = "";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const binaryBody =
    options.body instanceof Uint8Array || options.body instanceof Blob;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(binaryBody
        ? {}
        : { "Content-Type": "application/json" }),
      ...(options.headers ?? {}),
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const body: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message =
      typeof body === "object" && body && "error" in body
        ? String((body as { error?: { message?: string } }).error?.message)
        : response.statusText;
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}
