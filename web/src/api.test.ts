import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

describe("M10 API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends exact versioned workload configuration", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ operation: "deploy", resource: "deployment/kri-workload" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const configuration = {
      schema_version: "1.0" as const,
      cpu_request: "50m",
      cpu_limit: "100m",
      memory_request: "64Mi",
      memory_limit: "128Mi",
      replicas: 2,
    };

    await api.deployWorkload(configuration);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/workload",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(configuration) }),
    );
  });

  it("retains structured API failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "observation_conflict",
            message: "artifact already exists",
            details: ["choose a new ID"],
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const failure = await api
      .createObservation(
        {
          interval_start: "2026-11-01T10:00:00Z",
          interval_end: "2026-11-01T10:01:00Z",
          step_seconds: 5,
        },
        "obs-existing",
      )
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      operation: "Collect observation",
      status: 409,
      code: "observation_conflict",
      details: ["choose a new ID"],
    });
  });
});
