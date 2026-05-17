import assert from "node:assert/strict";
import worker from "./src/index.js";

const store = new Map();
const env = {
  FEED_CONFIG: {
    get: async (key) => store.get(key) || null,
    put: async (key, value) => store.set(key, value)
  },
  BROADCASTIFY_API_KEY: "test-key",
  BROADCASTIFY_FEED_ID: "45951",
  FEED_CONFIG_KEY: "current-feed",
  CACHE_SECONDS: "60",
  STREAM_URL_TTL_SECONDS: "300",
  UPDATE_TOKEN: "test-update-token"
};

globalThis.fetch = async () => new Response(
  JSON.stringify({
    Feed: [
      {
        id: 45951,
        descr: "Phillipsburg / Easton Public Safety",
        status: 1,
        listeners: 7,
        bitrate: 32,
        mount: "/test-mount",
        Relays: [
          {
            host: "relay.broadcastify.com",
            port: "80"
          }
        ]
      }
    ]
  }),
  {
    status: 200,
    headers: {
      "content-type": "application/json"
    }
  }
);

const response = await worker.fetch(new Request("https://radio.franksplex.com/current-feed.json"), env);
assert.equal(response.status, 200);
const config = await response.json();
assert.equal(config.feedId, "45951");
assert.equal(config.title, "Phillipsburg / Easton Public Safety");
assert.equal(config.streamUrl, "http://relay.broadcastify.com/test-mount");
assert.equal(config.source, "broadcastify-audio-api");

const healthResponse = await worker.fetch(new Request("https://radio.franksplex.com/health"), env);
assert.equal(healthResponse.status, 200);
const health = await healthResponse.json();
assert.equal(health.mode, "broadcastify-api");

const manualResponse = await worker.fetch(
  new Request("https://radio.franksplex.com/update", {
    method: "POST",
    headers: {
      "Authorization": "Bearer test-update-token",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      feedId: "45951",
      title: "Phillipsburg / Easton Public Safety",
      listeners: 3,
      bitrate: 32,
      streamUrl: "https://example.test/audio"
    })
  }),
  { ...env, BROADCASTIFY_API_KEY: "" }
);
assert.equal(manualResponse.status, 200);

console.log("worker tests ok");
