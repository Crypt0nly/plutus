#!/usr/bin/env node
/**
 * Plutus WhatsApp Bridge
 *
 * Communicates with the Python WhatsApp connector via JSON over stdin/stdout.
 * Uses whatsapp-web.js with LocalAuth for persistent sessions and phone-number
 * pairing (no QR scan required).
 *
 * Protocol (newline-delimited JSON):
 *   Python → Node  (commands):
 *     {"cmd": "send", "to": "<phone_or_name>", "text": "<message>"}
 *     {"cmd": "status"}
 *     {"cmd": "stop"}
 *
 *   Node → Python  (events):
 *     {"event": "ready", "info": {"name": "...", "phone": "..."}}
 *     {"event": "qr", "qr": "<qr_string>"}
 *     {"event": "pairing_code", "code": "<8-digit-code>"}
 *     {"event": "message", "from": "...", "from_name": "...", "text": "...", "timestamp": 0}
 *     {"event": "status", "state": "...", "ready": true/false}
 *     {"event": "disconnected", "reason": "..."}
 *     {"event": "error", "message": "..."}
 *     {"event": "send_result", "success": true/false, "message": "..."}
 */

"use strict";

const path = require("path");
const fs   = require("fs");

// ── Resolve whatsapp-web.js from the same directory as this script ──────────
const scriptDir = __dirname;
const wwjsPath  = path.join(scriptDir, "node_modules", "whatsapp-web.js");

if (!fs.existsSync(wwjsPath)) {
  emit({ event: "error", message: "whatsapp-web.js not installed. Run: npm install in the connectors directory." });
  process.exit(1);
}

const { Client, LocalAuth } = require(wwjsPath);

// ── Configuration from env ──────────────────────────────────────────────────
const SESSION_DIR   = process.env.WA_SESSION_DIR   || path.join(scriptDir, ".wwebjs_auth");
const PHONE_NUMBER  = process.env.WA_PHONE_NUMBER  || "";  // e.g. "4917612345678"
const CHROMIUM_PATH = process.env.WA_CHROMIUM_PATH || undefined;

// ── State ───────────────────────────────────────────────────────────────────
let client = null;
let isReady = false;
let currentState = "INITIALIZING";

// ── Emit helper ─────────────────────────────────────────────────────────────
function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

// ── Build puppeteer args ─────────────────────────────────────────────────────
function buildPuppeteerArgs() {
  const args = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--safebrowsing-disable-auto-update",
  ];
  const opts = {
    headless: true,
    args,
  };
  if (CHROMIUM_PATH) {
    opts.executablePath = CHROMIUM_PATH;
  }
  return opts;
}

// ── Initialize the WhatsApp client ──────────────────────────────────────────
function startClient() {
  const puppeteerOpts = buildPuppeteerArgs();

  // Use phone-number pairing if a phone number is provided
  const pairWithPhoneNumber = PHONE_NUMBER
    ? { phoneNumber: PHONE_NUMBER, showNotification: false }
    : undefined;

  client = new Client({
    authStrategy: new LocalAuth({
      dataPath: SESSION_DIR,
    }),
    puppeteer: puppeteerOpts,
    pairWithPhoneNumber,
    // Increase auth timeout to 5 minutes
    authTimeoutMs: 300000,
  });

  client.on("qr", (qr) => {
    currentState = "QR_PENDING";
    emit({ event: "qr", qr });
  });

  client.on("code", (code) => {
    currentState = "PAIRING_CODE_PENDING";
    emit({ event: "pairing_code", code });
  });

  client.on("loading_screen", (percent, message) => {
    currentState = "LOADING";
    emit({ event: "status", state: "LOADING", percent, message, ready: false });
  });

  client.on("authenticated", () => {
    currentState = "AUTHENTICATED";
    emit({ event: "status", state: "AUTHENTICATED", ready: false });
  });

  client.on("auth_failure", (msg) => {
    currentState = "AUTH_FAILURE";
    emit({ event: "error", message: `Authentication failed: ${msg}` });
  });

  client.on("ready", async () => {
    isReady = true;
    currentState = "READY";
    try {
      const info = client.info;
      emit({
        event: "ready",
        info: {
          name:  info.pushname || "",
          phone: info.wid ? info.wid.user : "",
        },
      });
    } catch {
      emit({ event: "ready", info: {} });
    }
  });

  client.on("message", async (msg) => {
    if (!msg.fromMe) {
      let fromName = "";
      try {
        const contact = await msg.getContact();
        fromName = contact.pushname || contact.name || "";
      } catch {
        fromName = "";
      }
      emit({
        event: "message",
        from: msg.from,
        from_name: fromName,
        text: msg.body,
        timestamp: msg.timestamp,
        is_group: msg.from.endsWith("@g.us"),
      });
    }
  });

  client.on("disconnected", (reason) => {
    isReady = false;
    currentState = "DISCONNECTED";
    emit({ event: "disconnected", reason });
  });

  client.on("change_state", (state) => {
    currentState = state;
    emit({ event: "status", state, ready: isReady });
  });

  client.initialize().catch((err) => {
    emit({ event: "error", message: `Failed to initialize: ${err.message || err}` });
    process.exit(1);
  });
}

// ── Send a message ───────────────────────────────────────────────────────────
async function sendMessage(to, text) {
  if (!isReady || !client) {
    emit({ event: "send_result", success: false, message: "Client not ready" });
    return;
  }
  try {
    // Normalize the phone number: strip non-digits, append @c.us if needed
    let chatId = to;
    if (!to.includes("@")) {
      const digits = to.replace(/\D/g, "");
      chatId = `${digits}@c.us`;
    }
    await client.sendMessage(chatId, text);
    emit({ event: "send_result", success: true, message: `Sent to ${to}` });
  } catch (err) {
    emit({ event: "send_result", success: false, message: err.message || String(err) });
  }
}

// ── Handle commands from Python ──────────────────────────────────────────────
let inputBuffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  inputBuffer += chunk;
  const lines = inputBuffer.split("\n");
  inputBuffer = lines.pop(); // keep incomplete line
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let cmd;
    try {
      cmd = JSON.parse(trimmed);
    } catch {
      emit({ event: "error", message: `Invalid JSON command: ${trimmed}` });
      continue;
    }
    handleCommand(cmd);
  }
});

function handleCommand(cmd) {
  switch (cmd.cmd) {
    case "send":
      sendMessage(cmd.to, cmd.text);
      break;
    case "status":
      emit({ event: "status", state: currentState, ready: isReady });
      break;
    case "stop":
      if (client) {
        client.destroy().finally(() => process.exit(0));
      } else {
        process.exit(0);
      }
      break;
    default:
      emit({ event: "error", message: `Unknown command: ${cmd.cmd}` });
  }
}

process.stdin.on("end", () => {
  if (client) client.destroy().finally(() => process.exit(0));
  else process.exit(0);
});

process.on("SIGTERM", () => {
  if (client) client.destroy().finally(() => process.exit(0));
  else process.exit(0);
});

process.on("SIGINT", () => {
  if (client) client.destroy().finally(() => process.exit(0));
  else process.exit(0);
});

// ── Start ────────────────────────────────────────────────────────────────────
startClient();
