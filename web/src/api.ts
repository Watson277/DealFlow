import type {
  Capability,
  Customer,
  KnowledgeDocument,
  Page,
  Proposal,
  Requirement,
  RFP,
  RFPStatus,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      if (
        body.detail &&
        typeof body.detail === "object" &&
        "message" in body.detail &&
        typeof body.detail.message === "string"
      ) {
        const title =
          "existing_title" in body.detail &&
          typeof body.detail.existing_title === "string"
            ? `：${body.detail.existing_title}`
            : "";
        message = `${body.detail.message}${title}`;
      }
      if (Array.isArray(body.detail)) {
        message = body.detail
          .map(
            (item: { loc?: string[]; msg?: string }) =>
              `${item.loc?.slice(1).join(".") ?? "字段"}：${item.msg ?? "格式不正确"}`,
          )
          .join("；");
      }
    } catch {
      // The status line remains the safest fallback for non-JSON failures.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function listAll<T>(path: string): Promise<Page<T>> {
  const items: T[] = [];
  let page: Page<T>;
  do {
    page = await request<Page<T>>(`${path}?limit=100&offset=${items.length}`);
    items.push(...page.items);
  } while (items.length < page.total && page.items.length > 0);
  return { items, total: page.total };
}

export const api = {
  deleteCustomer: (id: string) => request<void>(`/customers/${id}`, { method: "DELETE" }),
  deleteKnowledge: (id: string) => request<void>(`/knowledge/${id}`, { method: "DELETE" }),
  deleteRFP: (id: string) => request<void>(`/rfps/${id}`, { method: "DELETE" }),
  customers: () => listAll<Customer>("/customers"),
  createCustomer: (body: Record<string, unknown>) =>
    request<Customer>("/customers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  knowledge: () => listAll<KnowledgeDocument>("/knowledge"),
  createKnowledge: (body: FormData) =>
    request<KnowledgeDocument>("/knowledge", { method: "POST", body }),
  updateKnowledge: (id: string, body: FormData) =>
    request<KnowledgeDocument>(`/knowledge/${id}`, { method: "PUT", body }),
  rfps: () => listAll<RFP>("/rfps"),
  createRFP: (body: FormData) =>
    request<unknown>("/rfps", { method: "POST", body }),
  status: (id: string) => request<RFPStatus>(`/rfps/${id}/status`),
  retry: (id: string) =>
    request<unknown>(`/rfps/${id}/retry`, { method: "POST" }),
  requirements: (id: string) =>
    request<Page<Requirement>>(`/rfps/${id}/requirements`),
  capabilities: (id: string) =>
    request<Page<Capability>>(`/rfps/${id}/capabilities`),
  proposals: (id: string) => request<Page<Proposal>>(`/rfps/${id}/proposals`),
  markdown: async (id: string) => {
    const response = await fetch(`/proposals/${id}/markdown`);
    if (!response.ok)
      throw new Error(`${response.status} ${response.statusText}`);
    return response.text();
  },
  review: (id: string, decision: string, comment: string | null) =>
    request<unknown>(`/proposals/${id}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, comment }),
    }),
};
