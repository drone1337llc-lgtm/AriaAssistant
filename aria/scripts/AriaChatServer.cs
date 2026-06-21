using Godot;
using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;

namespace Aria
{
    /// <summary>
    /// Tiny HTTP/1.1 server that accepts a single endpoint: POST /chat
    /// with body {"text":"..."}. Forwards to LLMBridge.SendMessage so the
    /// same code path (directive queue, IK layer, body animation) is used
    /// regardless of where the message came from (F2 overlay, right-click,
    /// or the Streamlit dashboard on PC 2).
    ///
    /// Why not WebSocket? The dashboard only needs fire-and-forget messages.
    /// Plain HTTP POST is easier to call from Streamlit (st.requests.post) and
    /// doesn't require a long-lived connection.
    ///
    /// Why not reuse the Astro server? Aria talks to LM Studio directly
    /// via LLMBridge; the Astro server is for the legacy AstroBud system.
    /// Bridging them would mean two LLM roundtrips per message.
    ///
    /// Default port: 8767. Configurable via the [Port] export. The server
    /// logs every accepted request and any error. CORS is permissive
    /// (Access-Control-Allow-Origin: *) so the dashboard, which may run on
    /// a different host, can hit it from a browser if the user opens the
    /// dashboard remotely.
    /// </summary>
    public partial class AriaChatServer : Node
    {
        [Export] public int Port { get; set; } = 8767;
        [Export] public string BindAddress { get; set; } = "0.0.0.0";

        private Godot.TcpServer _server;
        private readonly List<Godot.StreamPeerTcp> _clients = new();

        // Set by Main when it instantiates the server. Keeps this node
        // ignorant of where the LLM lives (LLMBridge, mock, test, etc.).
        public Action<string> OnChatMessage;

        public override void _Ready()
        {
            _server = new Godot.TcpServer();
            var err = _server.Listen((ushort)Port, BindAddress);
            if (err != Error.Ok)
            {
                GD.PrintErr($"[ChatServer] listen failed on {BindAddress}:{Port}: {err}");
                return;
            }
            GD.Print($"[ChatServer] listening on http://{BindAddress}:{Port}/ (POST /chat)");
        }

        public override void _Process(double delta)
        {
            if (_server == null || !_server.IsListening()) return;

            // Accept new connections.
            while (_server.IsConnectionAvailable())
            {
                var conn = _server.TakeConnection();
                if (conn != null) _clients.Add(conn);
            }

            // Read what's already connected. We collect full requests first,
            // then parse them, then respond. The protocol is HTTP/1.1 with
            // Content-Length and no chunked encoding — plenty for a chat POST.
            for (int i = _clients.Count - 1; i >= 0; i--)
            {
                var peer = _clients[i];
                if (peer.GetStatus() == Godot.StreamPeerSocket.Status.Connected)
                {
                    var bytesAvailable = peer.GetAvailableBytes();
                    if (bytesAvailable > 0)
                    {
                        // Read as text since the protocol is HTTP/1.1 text.
                        var text = peer.GetString(bytesAvailable);
                        HandleRequest(peer, text);
                    }
                }
                else
                {
                    // Disconnected or errored — drop the client.
                    peer.Dispose();
                    _clients.RemoveAt(i);
                }
            }
        }

        public override void _ExitTree()
        {
            foreach (var c in _clients) { try { c.Dispose(); } catch { } }
            _clients.Clear();
            _server?.Stop();
            _server = null;
            GD.Print("[ChatServer] stopped");
        }

        private void HandleRequest(Godot.StreamPeerTcp peer, string text)
        {
            // Find the end of the headers (CRLFCRLF), then parse the body.
            int bodyStart = text.IndexOf("\r\n\r\n");
            if (bodyStart < 0)
            {
                // Haven't received the full request yet — wait for more data.
                return;
            }
            string head = text.Substring(0, bodyStart);
            string body = text.Substring(bodyStart + 4);

            // Parse the request line: METHOD PATH HTTP/1.1
            int firstSpace = head.IndexOf(' ');
            int secondSpace = head.IndexOf(' ', firstSpace + 1);
            string method = firstSpace > 0 ? head.Substring(0, firstSpace) : "";
            string path = (firstSpace > 0 && secondSpace > firstSpace)
                ? head.Substring(firstSpace + 1, secondSpace - firstSpace - 1)
                : "";

            // Find Content-Length so we know if we have the full body.
            int contentLength = 0;
            foreach (var line in head.Split("\r\n"))
            {
                int colon = line.IndexOf(':');
                if (colon > 0 && line.Substring(0, colon).Trim().Equals("Content-Length", StringComparison.OrdinalIgnoreCase))
                {
                    int.TryParse(line.Substring(colon + 1).Trim(), out contentLength);
                    break;
                }
            }
            // If the announced body is bigger than what we have, wait.
            if (body.Length < contentLength) return;

            // Route the request.
            string response = method switch
            {
                "OPTIONS" => CORSResponse(),
                "POST" when path == "/chat" => HandleChat(body),
                "POST"                     => NotFound("POST endpoint must be /chat"),
                "GET"  when path == "/healthz" => TextResponse(200, "ok\n", "text/plain"),
                "GET"                      => NotFound("GET endpoint must be /healthz"),
                _                          => NotFound($"{method} {path} not supported"),
            };

            // Send response.
            peer.PutUtf8String(response);
        }

        private string HandleChat(string body)
        {
            if (OnChatMessage == null)
            {
                return JsonResponse(503, new { ok = false, error = "no LLM wired" });
            }
            try
            {
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                if (!root.TryGetProperty("text", out var tv) || tv.ValueKind != JsonValueKind.String)
                {
                    return JsonResponse(400, new { ok = false, error = "missing 'text' string" });
                }
                string userText = tv.GetString();
                if (string.IsNullOrWhiteSpace(userText))
                {
                    return JsonResponse(400, new { ok = false, error = "empty 'text'" });
                }
                GD.Print($"[ChatServer] /chat ← \"{userText}\"");
                OnChatMessage(userText);
                return JsonResponse(200, new { ok = true, queued = userText.Length });
            }
            catch (Exception e)
            {
                GD.PrintErr($"[ChatServer] /chat parse error: {e.Message}");
                return JsonResponse(400, new { ok = false, error = e.Message });
            }
        }

        // ── Response helpers ─────────────────────────────────────────────

        private static string JsonResponse(int code, object payload) =>
            TextResponse(code, JsonSerializer.Serialize(payload), "application/json");

        private static string TextResponse(int code, string body, string contentType)
        {
            string status = code switch
            {
                200 => "OK",
                400 => "Bad Request",
                404 => "Not Found",
                503 => "Service Unavailable",
                _   => "OK",
            };
            return $"HTTP/1.1 {code} {status}\r\n" +
                   $"Content-Type: {contentType}\r\n" +
                   $"Content-Length: {Encoding.UTF8.GetByteCount(body)}\r\n" +
                   $"Access-Control-Allow-Origin: *\r\n" +
                   $"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n" +
                   $"Access-Control-Allow-Headers: Content-Type\r\n" +
                   $"Connection: close\r\n\r\n" +
                   body;
        }

        private static string NotFound(string msg) => JsonResponse(404, new { ok = false, error = msg });
        private static string CORSResponse()   => TextResponse(204, "", "text/plain");
    }
}
