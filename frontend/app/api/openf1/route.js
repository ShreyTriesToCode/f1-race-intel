export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const OPENF1_BASE = "https://api.openf1.org/v1";

function isSafeEndpoint(endpoint) {
  return /^[a-zA-Z0-9_/-]+$/.test(endpoint || "");
}

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const endpoint = searchParams.get("endpoint");

  if (!isSafeEndpoint(endpoint)) {
    return Response.json(
      { ok: false, error: "Invalid or missing OpenF1 endpoint." },
      { status: 400 }
    );
  }

  const upstream = new URL(`${OPENF1_BASE}/${endpoint.replace(/^\/+/, "")}`);
  for (const [key, value] of searchParams.entries()) {
    if (key !== "endpoint" && value !== "") {
      upstream.searchParams.append(key, value);
    }
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);

  try {
    const res = await fetch(upstream.toString(), {
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "User-Agent": "f1-race-intel-live-dashboard/1.0"
      },
      cache: "no-store"
    });

    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }

    return Response.json(
      {
        ok: res.ok,
        status: res.status,
        source: "OpenF1",
        url: upstream.toString(),
        data
      },
      {
        status: res.ok ? 200 : 200,
        headers: {
          "Cache-Control": "no-store"
        }
      }
    );
  } catch (error) {
    return Response.json(
      {
        ok: false,
        source: "OpenF1",
        error: error?.name === "AbortError" ? "OpenF1 request timed out." : String(error?.message || error)
      },
      {
        status: 200,
        headers: {
          "Cache-Control": "no-store"
        }
      }
    );
  } finally {
    clearTimeout(timeout);
  }
}
