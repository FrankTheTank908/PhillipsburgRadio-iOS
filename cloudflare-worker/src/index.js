const DEFAULT_KEY = "current-feed";
const DEFAULT_API_BASE_URL = "https://api.broadcastify.com/audio/";
const DEFAULT_CACHE_SECONDS = 60;
const DEFAULT_STREAM_URL_TTL_SECONDS = 300;
const DEFAULT_FORCE_REFRESH_MIN_SECONDS = 15;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse(
        {
          ok: true,
          mode: isBroadcastifyApiConfigured(env) ? "broadcastify-api" : "manual-update-fallback",
          feedId: env.BROADCASTIFY_FEED_ID || null
        },
        200
      );
    }

    if (request.method === "GET" && isConfigPath(url.pathname)) {
      return getCurrentConfig(request, env);
    }

    if (request.method === "POST" && url.pathname === "/refresh") {
      return refreshCurrentConfig(request, env);
    }

    if ((request.method === "POST" || request.method === "PUT") && url.pathname === "/update") {
      return updateCurrentConfig(request, env);
    }

    return jsonResponse({ error: "Not found" }, 404);
  }
};

function isConfigPath(pathname) {
  return pathname === "/" || pathname === "/current-feed.json" || pathname === "/config";
}

async function getCurrentConfig(request, env) {
  assertConfigured(env);

  if (isBroadcastifyApiConfigured(env)) {
    return getBroadcastifyApiConfig(request, env);
  }

  const key = env.FEED_CONFIG_KEY || DEFAULT_KEY;
  const stored = await env.FEED_CONFIG.get(key);

  if (!stored) {
    return jsonResponse(
      {
        error: "No feed config has been uploaded yet",
        expectedUpdatePath: "/update"
      },
      404
    );
  }

  return new Response(stored, {
    status: 200,
    headers: {
      ...corsHeaders(),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}

async function getBroadcastifyApiConfig(request, env) {
  const url = new URL(request.url);
  const forceRefresh = url.searchParams.get("refresh") === "1" || url.searchParams.get("force") === "1";
  const cached = await readStoredConfig(env);

  if (cached && !shouldRefresh(cached, forceRefresh, env)) {
    return jsonResponse(cached.config, 200);
  }

  try {
    const config = await fetchBroadcastifyFeedConfig(env);
    await writeStoredConfig(env, config);
    return jsonResponse(config, 200);
  } catch (error) {
    if (cached) {
      return jsonResponse(
        {
          ...cached.config,
          message: `Using cached stream URL because Broadcastify API refresh failed: ${error.message}`
        },
        200
      );
    }

    return jsonResponse(
      {
        error: "Broadcastify API refresh failed",
        message: error.message
      },
      502
    );
  }
}

async function refreshCurrentConfig(request, env) {
  assertConfigured(env);

  if (!isAuthorized(request, env.UPDATE_TOKEN)) {
    return jsonResponse({ error: "Unauthorized" }, 401);
  }

  if (!isBroadcastifyApiConfigured(env)) {
    return jsonResponse({ error: "Broadcastify API secrets are not configured" }, 400);
  }

  try {
    const config = await fetchBroadcastifyFeedConfig(env);
    await writeStoredConfig(env, config);
    return jsonResponse({ ok: true, config }, 200);
  } catch (error) {
    return jsonResponse({ ok: false, error: error.message }, 502);
  }
}

async function updateCurrentConfig(request, env) {
  assertConfigured(env);

  if (!isAuthorized(request, env.UPDATE_TOKEN)) {
    return jsonResponse({ error: "Unauthorized" }, 401);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "Request body must be JSON" }, 400);
  }

  const validationError = validateConfig(body);
  if (validationError) {
    return jsonResponse({ error: validationError }, 400);
  }

  const now = new Date();
  const config = {
    feedId: body.feedId || env.BROADCASTIFY_FEED_ID || "45951",
    title: body.title || "Phillipsburg / Easton Public Safety",
    status: body.status || "unknown",
    listeners: Number.isFinite(Number(body.listeners)) ? Number(body.listeners) : null,
    bitrate: Number.isFinite(Number(body.bitrate)) ? Number(body.bitrate) : null,
    streamUrl: body.streamUrl,
    updatedAt: body.updatedAt || now.toISOString(),
    expiresAt: body.expiresAt || null,
    source: body.source || "manual-update",
    message: body.message || null
  };

  const key = env.FEED_CONFIG_KEY || DEFAULT_KEY;
  await env.FEED_CONFIG.put(key, JSON.stringify(config, null, 2));

  return jsonResponse({ ok: true, key, config }, 200);
}

async function fetchBroadcastifyFeedConfig(env) {
  const feedId = String(env.BROADCASTIFY_FEED_ID || "").trim();
  const apiKey = String(env.BROADCASTIFY_API_KEY || "").trim();

  if (!feedId) {
    throw new Error("Missing BROADCASTIFY_FEED_ID");
  }

  if (!apiKey) {
    throw new Error("Missing BROADCASTIFY_API_KEY secret");
  }

  const apiUrl = new URL(env.BROADCASTIFY_API_BASE_URL || DEFAULT_API_BASE_URL);
  apiUrl.searchParams.set("a", "feed");
  apiUrl.searchParams.set("feedId", feedId);
  apiUrl.searchParams.set("type", "json");
  apiUrl.searchParams.set("key", apiKey);

  const response = await fetch(apiUrl.toString(), {
    headers: {
      "Accept": "application/json",
      "User-Agent": "PhillipsburgRadio/1.0"
    },
    cf: {
      cacheTtl: 0,
      cacheEverything: false
    }
  });

  const bodyText = await response.text();

  if (!response.ok) {
    throw new Error(`Broadcastify API returned HTTP ${response.status}: ${bodyText.slice(0, 200)}`);
  }

  let payload;
  try {
    payload = JSON.parse(bodyText);
  } catch {
    throw new Error(`Broadcastify API did not return JSON: ${bodyText.slice(0, 200)}`);
  }

  const feed = findFeedObject(payload);
  if (!feed) {
    throw new Error("Broadcastify API response did not include a feed object");
  }

  const streamUrl = resolveStreamUrl(feed);
  const now = new Date();
  const ttlSeconds = numberFromEnv(env.STREAM_URL_TTL_SECONDS, DEFAULT_STREAM_URL_TTL_SECONDS);

  return {
    feedId: String(firstValue(feed, ["id", "feedId", "feed_id"]) || feedId),
    title: firstValue(feed, ["descr", "description", "name", "title"]) || "Phillipsburg / Easton Public Safety",
    status: normalizeStatus(firstValue(feed, ["status", "online"])),
    listeners: numberOrNull(firstValue(feed, ["listeners", "listenerCount", "listener_count"])),
    bitrate: numberOrNull(firstValue(feed, ["bitrate", "bitRate", "bit_rate"])),
    streamUrl,
    updatedAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + ttlSeconds * 1000).toISOString(),
    source: "broadcastify-audio-api",
    message: null
  };
}

function findFeedObject(payload) {
  const candidates = [
    payload?.Feed,
    payload?.feed,
    payload?.feeds,
    payload?.Feeds,
    payload?.data,
    payload
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0 && typeof candidate[0] === "object") {
      return candidate[0];
    }

    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      if (candidate.Feed || candidate.feed || candidate.feeds || candidate.Feeds || candidate.data) {
        continue;
      }

      return candidate;
    }
  }

  return null;
}

function resolveStreamUrl(feed) {
  const directUrl = firstValue(feed, [
    "streamUrl",
    "streamURL",
    "stream_url",
    "url",
    "listenUrl",
    "listenURL",
    "listen_url"
  ]);

  if (directUrl && looksLikeUrl(directUrl)) {
    return directUrl;
  }

  const mount = firstValue(feed, ["mount", "mountPoint", "mountpoint", "mount_point"]);
  const relay = firstRelay(feed);

  if (!mount || !relay?.host) {
    throw new Error("Broadcastify API response did not include a direct URL or relay/mount fields");
  }

  if (looksLikeUrl(mount)) {
    return mount;
  }

  const port = String(firstValue(relay, ["port"]) || "").trim();
  const scheme = port === "443" ? "https" : "http";
  const host = String(relay.host).replace(/^https?:\/\//, "").replace(/\/$/, "");
  const normalizedMount = String(mount).startsWith("/") ? String(mount) : `/${mount}`;
  const portPart = port && !["80", "443"].includes(port) ? `:${port}` : "";

  return `${scheme}://${host}${portPart}${normalizedMount}`;
}

function firstRelay(feed) {
  const relays = firstValue(feed, ["Relays", "relays", "Relay", "relay"]);

  if (Array.isArray(relays) && relays.length > 0) {
    return relays[0];
  }

  if (relays && typeof relays === "object") {
    return relays;
  }

  const host = firstValue(feed, ["host", "server", "relayHost", "relay_host"]);
  const port = firstValue(feed, ["port", "serverPort", "server_port", "relayPort", "relay_port"]);

  if (host) {
    return { host, port };
  }

  return null;
}

function firstValue(object, keys) {
  if (!object || typeof object !== "object") {
    return null;
  }

  for (const key of keys) {
    const value = object[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return value;
    }
  }

  return null;
}

function looksLikeUrl(value) {
  return /^https?:\/\//i.test(String(value));
}

function normalizeStatus(value) {
  if (value === 1 || value === "1" || value === true || String(value).toLowerCase() === "online") {
    return "online";
  }

  if (value === 0 || value === "0" || value === false || String(value).toLowerCase() === "offline") {
    return "offline";
  }

  return value == null ? "unknown" : String(value);
}

function numberOrNull(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

async function readStoredConfig(env) {
  const key = env.FEED_CONFIG_KEY || DEFAULT_KEY;
  const stored = await env.FEED_CONFIG.get(key);

  if (!stored) {
    return null;
  }

  try {
    return {
      config: JSON.parse(stored),
      raw: stored
    };
  } catch {
    return null;
  }
}

async function writeStoredConfig(env, config) {
  const key = env.FEED_CONFIG_KEY || DEFAULT_KEY;
  await env.FEED_CONFIG.put(key, JSON.stringify(config, null, 2));
}

function shouldRefresh(cached, forceRefresh, env) {
  const config = cached.config;
  const now = Date.now();
  const updatedAt = Date.parse(config.updatedAt || "");
  const expiresAt = Date.parse(config.expiresAt || "");
  const cacheSeconds = numberFromEnv(env.CACHE_SECONDS, DEFAULT_CACHE_SECONDS);
  const forceMinSeconds = numberFromEnv(env.FORCE_REFRESH_MIN_SECONDS, DEFAULT_FORCE_REFRESH_MIN_SECONDS);

  if (Number.isFinite(expiresAt) && expiresAt <= now) {
    return true;
  }

  if (forceRefresh) {
    return !Number.isFinite(updatedAt) || now - updatedAt >= forceMinSeconds * 1000;
  }

  if (!Number.isFinite(updatedAt)) {
    return true;
  }

  return now - updatedAt >= cacheSeconds * 1000;
}

function isBroadcastifyApiConfigured(env) {
  return Boolean(String(env.BROADCASTIFY_API_KEY || "").trim() && String(env.BROADCASTIFY_FEED_ID || "").trim());
}

function numberFromEnv(value, fallback) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : fallback;
}

function validateConfig(body) {
  if (!body || typeof body !== "object") {
    return "Config must be a JSON object";
  }

  if (typeof body.streamUrl !== "string" || body.streamUrl.trim() === "") {
    return "streamUrl is required";
  }

  let streamUrl;
  try {
    streamUrl = new URL(body.streamUrl);
  } catch {
    return "streamUrl must be a valid URL";
  }

  if (streamUrl.protocol !== "https:" && streamUrl.protocol !== "http:") {
    return "streamUrl must use http or https";
  }

  return null;
}

function isAuthorized(request, expectedToken) {
  if (!expectedToken) {
    return false;
  }

  const authorization = request.headers.get("Authorization") || "";
  const bearer = authorization.startsWith("Bearer ") ? authorization.slice(7).trim() : "";
  const headerToken = request.headers.get("X-Update-Token") || "";

  return constantTimeEqual(bearer, expectedToken) || constantTimeEqual(headerToken, expectedToken);
}

function constantTimeEqual(a, b) {
  if (!a || !b || a.length !== b.length) {
    return false;
  }

  let result = 0;
  for (let index = 0; index < a.length; index += 1) {
    result |= a.charCodeAt(index) ^ b.charCodeAt(index);
  }

  return result === 0;
}

function assertConfigured(env) {
  if (!env.FEED_CONFIG) {
    throw new Error("Missing FEED_CONFIG KV binding");
  }
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      ...corsHeaders(),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Update-Token"
  };
}
