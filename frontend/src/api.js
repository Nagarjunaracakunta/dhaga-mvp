// Every call to the backend lives here. Errors come back as ApiError with the backend's code + message.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request(path, { method = "GET", body, params } = {}) {
  const query = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString()
    : "";
  let res;
  try {
    res = await fetch(`${BASE}${path}${query === "?" ? "" : query}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("NETWORK", "Can't reach the backend. Is uvicorn running on port 8000?", 0);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(data?.error?.code ?? `HTTP_${res.status}`, data?.error?.message ?? res.statusText, res.status);
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),

  // CX Copilot
  tickets: (params) => request("/api/cx/tickets", { params }),
  ticket: (ref) => request(`/api/cx/tickets/${encodeURIComponent(ref)}`),
  analyze: (ref) => request(`/api/cx/tickets/${encodeURIComponent(ref)}/analyze`, { method: "POST" }),
  decide: (ref, body) => request(`/api/cx/tickets/${encodeURIComponent(ref)}/decision`, { method: "POST", body }),
  analyzeText: (body) => request("/api/cx/analyze", { method: "POST", body }),
  order: (number) => request(`/api/cx/orders/${encodeURIComponent(number)}`),
  cxMetrics: () => request("/api/cx/metrics"),

  // Returns Insights
  returnsSummary: () => request("/api/returns/summary"),
  returnsInsights: () => request("/api/returns/insights"),
  returnsProducts: () => request("/api/returns/products"),
  returnsBreakdown: (by) => request("/api/returns/breakdown", { params: { by } }),
  returnsReasons: () => request("/api/returns/reasons"),
  returnsRejected: () => request("/api/returns/rejected"),
  returnsClassify: (body = {}) => request("/api/returns/classify", { method: "POST", body }),
  returnsReviewQueue: (params) => request("/api/returns/review-queue", { params }),
  returnsReview: (returnId, category) =>
    request(`/api/returns/${encodeURIComponent(returnId)}/review`, { method: "POST", body: { category } }),

  // Returns investigation briefs
  returnsBriefs: () => request("/api/returns/briefs"),
  returnsGenerateBriefs: ({ topK = 5 } = {}) =>
    request("/api/returns/briefs", { method: "POST", body: { top_k: topK } }),
  returnsBriefReview: (insightId, status, note) =>
    request(`/api/returns/briefs/${encodeURIComponent(insightId)}/review`,
      { method: "POST", body: { status, reviewer: "neha", note } }),
};
