/**
 * OASIS — Tests for the frontend API client utility.
 *
 * Uses fetch mocking — no backend needed.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  studies,
  agents,
  sessions,
  auth,
  widget,
  participants,
  knowledge,
  settingsApi,
} from "./api";

// ── Mock fetch ──────────────────────────────────────────────────

const originalFetch = globalThis.fetch;

function mockFetch(response: unknown, status = 200, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": contentType }),
    json: () => Promise.resolve(response),
    text: () => Promise.resolve(JSON.stringify(response)),
  });
}

// ── Token Management ─────────────────────────────────────────────

describe("Auth Token Management", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("stores and retrieves token", () => {
    setAuthToken("test-token-123");
    expect(getAuthToken()).toBe("test-token-123");
  });

  it("returns null when no token set", () => {
    expect(getAuthToken()).toBeNull();
  });

  it("clears token", () => {
    setAuthToken("test-token-123");
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });
});

// ── Studies API ──────────────────────────────────────────────────

describe("Studies API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists studies", async () => {
    const data = [{ id: "1", title: "Study A" }];
    globalThis.fetch = mockFetch(data);

    const result = await studies.list();
    expect(result).toEqual(data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it("gets a study by ID", async () => {
    const data = { id: "abc", title: "My Study" };
    globalThis.fetch = mockFetch(data);

    const result = await studies.get("abc");
    expect(result.id).toBe("abc");
  });

  it("creates a study", async () => {
    const data = { id: "new-id", title: "New Study" };
    globalThis.fetch = mockFetch(data, 201);

    const result = await studies.create({ title: "New Study" });
    expect(result.title).toBe("New Study");

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.title).toBe("New Study");
  });

  it("updates a study", async () => {
    const data = { id: "abc", title: "Updated" };
    globalThis.fetch = mockFetch(data);

    const result = await studies.update("abc", { title: "Updated" });
    expect(result.title).toBe("Updated");
  });

  it("deletes a study", async () => {
    globalThis.fetch = mockFetch(undefined, 204);

    await studies.delete("abc"); // Should not throw
  });
});

// ── Agents API ──────────────────────────────────────────────────

describe("Agents API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists agents for a study", async () => {
    const data = [{ id: "a1", name: "Agent 1" }];
    globalThis.fetch = mockFetch(data);

    const result = await agents.list("study-1");
    expect(result).toEqual(data);
  });

  it("creates an agent", async () => {
    const data = { id: "new-agent", name: "Bot" };
    globalThis.fetch = mockFetch(data, 201);

    const result = await agents.create("study-1", { name: "Bot" });
    expect(result.name).toBe("Bot");
  });
});

// ── Sessions API ────────────────────────────────────────────────

describe("Sessions API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists sessions", async () => {
    const data = [{ id: "s1", status: "completed" }];
    globalThis.fetch = mockFetch(data);

    const result = await sessions.list("study-1", "agent-1");
    expect(result).toEqual(data);
  });

  it("lists sessions with filters", async () => {
    globalThis.fetch = mockFetch([]);

    await sessions.list("s1", "a1", { status: "completed", sort_by: "created_at" });
    const url = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(url).toContain("status=completed");
    expect(url).toContain("sort_by=created_at");
  });

  it("gets session stats", async () => {
    const data = { total_sessions: 10, completion_rate: 80.0 };
    globalThis.fetch = mockFetch(data);

    const result = await sessions.stats("s1", "a1");
    expect(result.total_sessions).toBe(10);
  });

  it("generates CSV export URL", () => {
    const url = sessions.exportCsvUrl("s1", "a1");
    expect(url).toContain("/sessions/export/csv");
  });

  it("generates JSON export URL", () => {
    const url = sessions.exportJsonUrl("s1", "a1");
    expect(url).toContain("/sessions/export/json");
  });

  it("generates export URL with filters", () => {
    const url = sessions.exportCsvUrl("s1", "a1", { status: "completed" });
    expect(url).toContain("status=completed");
  });
});

// ── Auth API ────────────────────────────────────────────────────

describe("Auth API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends login request", async () => {
    const data = { token: "jwt-token", username: "admin", expires_in: 86400 };
    globalThis.fetch = mockFetch(data);

    const result = await auth.login("admin", "password");
    expect(result.token).toBe("jwt-token");

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.username).toBe("admin");
    expect(body.password).toBe("password");
  });

  it("checks auth status", async () => {
    const data = { auth_enabled: false, authenticated: true, username: null };
    globalThis.fetch = mockFetch(data);

    const result = await auth.status();
    expect(result.auth_enabled).toBe(false);
  });
});

// ── Widget API ──────────────────────────────────────────────────

describe("Widget API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("fetches widget config", async () => {
    const data = {
      widget_key: "abc123",
      widget_title: "Survey",
      widget_primary_color: "#000000",
      participant_id_mode: "random",
    };
    globalThis.fetch = mockFetch(data);

    const result = await widget.config("abc123");
    expect(result.widget_key).toBe("abc123");
  });
});

// ── Participants API ─────────────────────────────────────────────

describe("Participants API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists participants", async () => {
    const data = [{ id: "p1", identifier: "P001" }];
    globalThis.fetch = mockFetch(data);

    const result = await participants.list("s1", "a1");
    expect(result).toEqual(data);
  });

  it("creates a participant", async () => {
    const data = { id: "p-new", identifier: "P001", used: false };
    globalThis.fetch = mockFetch(data, 201);

    const result = await participants.create("s1", "a1", {
      identifier: "P001",
    });
    expect(result.identifier).toBe("P001");
  });

  it("bulk creates participants", async () => {
    const data = [
      { id: "p1", identifier: "P001" },
      { id: "p2", identifier: "P002" },
    ];
    globalThis.fetch = mockFetch(data, 201);

    const result = await participants.bulkCreate("s1", "a1", ["P001", "P002"]);
    expect(result).toHaveLength(2);
  });
});

// ── Knowledge API ────────────────────────────────────────────────

describe("Knowledge API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists documents", async () => {
    const data = [{ id: "d1", title: "Doc 1" }];
    globalThis.fetch = mockFetch(data);

    const result = await knowledge.list("s1");
    expect(result).toEqual(data);
  });

  it("uploads text", async () => {
    const data = { id: "d-new", title: "New Doc", chunk_count: 3 };
    globalThis.fetch = mockFetch(data, 201);

    const result = await knowledge.uploadText("s1", {
      title: "New Doc",
      content: "Content here",
    });
    expect(result.title).toBe("New Doc");
  });

  it("searches knowledge base", async () => {
    const data = [{ content: "Result", title: "Doc", similarity: 0.95 }];
    globalThis.fetch = mockFetch(data);

    const result = await knowledge.search("s1", "test query");
    expect(result[0].similarity).toBe(0.95);
  });
});

// ── Settings API ─────────────────────────────────────────────────

describe("Settings API", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("gets API keys", async () => {
    const data = {
      keys: [
        {
          field: "openai_api_key",
          env_var: "OPENAI_API_KEY",
          is_set: true,
          source: "env",
          masked_value: "••••1234",
        },
      ],
    };
    globalThis.fetch = mockFetch(data);

    const result = await settingsApi.getKeys();
    expect(result.keys[0].field).toBe("openai_api_key");
  });

  it("updates API keys", async () => {
    const data = { keys: [] };
    globalThis.fetch = mockFetch(data);

    const result = await settingsApi.updateKeys({
      openai_api_key: "sk-new-key",
    });
    expect(result).toBeDefined();
  });
});

// ── Request Auth Headers ─────────────────────────────────────────

describe("Request sends auth headers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.clear();
  });

  it("includes Bearer token when set", async () => {
    setAuthToken("my-jwt-token");
    globalThis.fetch = mockFetch([]);

    await studies.list();

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = fetchCall[1].headers;
    expect(headers.Authorization).toBe("Bearer my-jwt-token");
  });

  it("omits Authorization header when no token", async () => {
    globalThis.fetch = mockFetch([]);

    await studies.list();

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = fetchCall[1].headers;
    expect(headers.Authorization).toBeUndefined();
  });
});
