import express, { Request, Response } from "express";
import { WebSocketServer, WebSocket } from "ws";
import { Client, LocalAuth, Message } from "whatsapp-web.js";
import qrcode from "qrcode-terminal";

const app = express();
app.use(express.json());

const REST_PORT = 8080;
const WS_PORT = 8081;

// Store connected WebSocket clients
const wsClients: Set<WebSocket> = new Set();

// Initialize WhatsApp client with persistent session
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "../data/whatsapp-session" }),
  puppeteer: {
    headless: true,
    executablePath: process.env.CHROME_PATH || "/Users/yonigo/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--no-zygote",
      "--disable-gpu",
      "--disable-crashpad",
    ],
  },
});

let isReady = false;

// QR code for authentication
client.on("qr", (qr: string) => {
  console.log("Scan this QR code to authenticate:");
  qrcode.generate(qr, { small: true });

  // Also broadcast QR to WebSocket clients
  broadcast({
    type: "qr",
    qr: qr,
  });
});

client.on("ready", () => {
  console.log("WhatsApp client is ready!");
  isReady = true;
  broadcast({ type: "ready" });
});

client.on("authenticated", () => {
  console.log("WhatsApp client authenticated");
  broadcast({ type: "authenticated" });
});

client.on("auth_failure", (msg: string) => {
  console.error("Authentication failed:", msg);
  broadcast({ type: "auth_failure", message: msg });
});

client.on("disconnected", (reason: string) => {
  console.log("WhatsApp client disconnected:", reason);
  isReady = false;
  broadcast({ type: "disconnected", reason });
});

// Handle incoming messages
client.on("message", async (message: Message) => {
  console.log(`Message from ${message.from}: ${message.body}`);

  const payload = {
    type: "incoming_message",
    from: message.from,
    body: message.body,
    timestamp: message.timestamp,
    chatId: message.from,
    hasMedia: message.hasMedia,
    isForwarded: message.isForwarded,
  };

  broadcast(payload);
});

// Broadcast to all WebSocket clients
function broadcast(data: object): void {
  const message = JSON.stringify(data);
  wsClients.forEach((ws) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(message);
    }
  });
}

// REST API Endpoints

// Health check
app.get("/api/health", (_req: Request, res: Response) => {
  res.json({
    status: "ok",
    whatsappReady: isReady,
  });
});

// Get connection status
app.get("/api/status", (_req: Request, res: Response) => {
  res.json({
    ready: isReady,
    state: client.info ? "connected" : "disconnected",
  });
});

// Send a message
app.post("/api/messages/send", async (req: Request, res: Response) => {
  const { phoneNumber, message } = req.body;

  if (!phoneNumber || !message) {
    res.status(400).json({ success: false, error: "phoneNumber and message are required" });
    return;
  }

  if (!isReady) {
    res.status(503).json({ success: false, error: "WhatsApp client not ready" });
    return;
  }

  try {
    // Format chat ID (add @c.us suffix if not present)
    const chatId = phoneNumber.includes("@c.us") ? phoneNumber : `${phoneNumber}@c.us`;

    await client.sendMessage(chatId, message);
    console.log(`Message sent to ${chatId}`);

    res.json({ success: true, chatId });
  } catch (error) {
    console.error("Error sending message:", error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

// Verify if a number is on WhatsApp
app.get("/api/contacts/verify/:phone", async (req: Request, res: Response) => {
  const { phone } = req.params;

  if (!isReady) {
    res.status(503).json({ exists: false, error: "WhatsApp client not ready" });
    return;
  }

  try {
    const numberId = await client.getNumberId(phone);
    res.json({
      exists: !!numberId,
      numberId: numberId?._serialized || null,
    });
  } catch (error) {
    console.error("Error verifying number:", error);
    res.status(500).json({
      exists: false,
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

// Get chat history
app.get("/api/chats/:chatId/messages", async (req: Request, res: Response) => {
  const { chatId } = req.params;
  const limit = parseInt(req.query.limit as string) || 50;

  if (!isReady) {
    res.status(503).json({ error: "WhatsApp client not ready" });
    return;
  }

  try {
    const formattedChatId = chatId.includes("@c.us") ? chatId : `${chatId}@c.us`;
    const chat = await client.getChatById(formattedChatId);
    const messages = await chat.fetchMessages({ limit });

    res.json({
      messages: messages.map((m) => ({
        id: m.id._serialized,
        body: m.body,
        fromMe: m.fromMe,
        timestamp: m.timestamp,
        hasMedia: m.hasMedia,
      })),
    });
  } catch (error) {
    console.error("Error fetching messages:", error);
    res.status(500).json({
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

// Get all chats
app.get("/api/chats", async (_req: Request, res: Response) => {
  if (!isReady) {
    res.status(503).json({ error: "WhatsApp client not ready" });
    return;
  }

  try {
    const chats = await client.getChats();
    res.json({
      chats: chats.slice(0, 50).map((chat) => ({
        id: chat.id._serialized,
        name: chat.name,
        isGroup: chat.isGroup,
        unreadCount: chat.unreadCount,
        timestamp: chat.timestamp,
      })),
    });
  } catch (error) {
    console.error("Error fetching chats:", error);
    res.status(500).json({
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

// Start servers
const server = app.listen(REST_PORT, () => {
  console.log(`REST API server running on port ${REST_PORT}`);
});

const wss = new WebSocketServer({ port: WS_PORT });

wss.on("connection", (ws: WebSocket) => {
  console.log("New WebSocket client connected");
  wsClients.add(ws);

  // Send current status to new client
  ws.send(
    JSON.stringify({
      type: "status",
      ready: isReady,
    })
  );

  ws.on("close", () => {
    console.log("WebSocket client disconnected");
    wsClients.delete(ws);
  });

  ws.on("error", (error) => {
    console.error("WebSocket error:", error);
    wsClients.delete(ws);
  });
});

console.log(`WebSocket server running on port ${WS_PORT}`);

// Initialize WhatsApp client
console.log("Initializing WhatsApp client...");
client.initialize();

// Graceful shutdown
process.on("SIGINT", async () => {
  console.log("Shutting down...");
  await client.destroy();
  server.close();
  wss.close();
  process.exit(0);
});
