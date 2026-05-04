export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function isAllowedAudioUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && (
      parsed.hostname.includes("openf1") ||
      parsed.hostname.includes("amazonaws.com") ||
      parsed.hostname.includes("cloudfront.net")
    );
  } catch {
    return false;
  }
}

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const url = searchParams.get("url");

  if (!url || !isAllowedAudioUrl(url)) {
    return Response.json(
      { ok: false, error: "Invalid or unsupported audio URL." },
      { status: 400 }
    );
  }

  const headers = {};
  const range = request.headers.get("range");
  if (range) headers.Range = range;

  try {
    const res = await fetch(url, {
      headers: {
        ...headers,
        "User-Agent": "f1-race-intel-audio-proxy/1.0"
      },
      cache: "no-store"
    });

    const outHeaders = new Headers();
    const contentType = res.headers.get("content-type") || "audio/mpeg";
    outHeaders.set("Content-Type", contentType);
    outHeaders.set("Cache-Control", "no-store");
    outHeaders.set("Accept-Ranges", "bytes");

    const contentLength = res.headers.get("content-length");
    const contentRange = res.headers.get("content-range");
    if (contentLength) outHeaders.set("Content-Length", contentLength);
    if (contentRange) outHeaders.set("Content-Range", contentRange);

    return new Response(res.body, {
      status: res.status,
      headers: outHeaders
    });
  } catch (error) {
    return Response.json(
      { ok: false, error: String(error?.message || error) },
      { status: 502 }
    );
  }
}
