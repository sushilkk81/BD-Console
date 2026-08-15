import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: { path: string[] };
};

async function proxy(request: NextRequest, context: RouteContext) {
  const apiUrl = process.env.API_URL;
  if (!apiUrl) {
    return Response.json(
      { detail: "API_URL is not configured" },
      { status: 500 }
    );
  }

  const upstreamPath = context.params.path.map(encodeURIComponent).join("/");
  const upstreamUrl = new URL(upstreamPath, `${apiUrl}/`);
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");

  try {
    const response = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");
    responseHeaders.delete("transfer-encoding");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("API proxy request failed", error);
    return Response.json({ detail: "Backend unavailable" }, { status: 502 });
  }
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
