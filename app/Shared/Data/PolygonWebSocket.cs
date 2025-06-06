using System.Net.WebSockets;
using System.Text;
using System.Diagnostics;
using Windows.Media.ClosedCaptioning;
using Windows.Media.Protection.PlayReady;
using System.Text.Json;
using BullseyeDesktop.Shared.Analyzers;

namespace BullseyeDesktop.Shared.Data
{
    public class PolygonWebSocket
    {
        public PolygonWebSocket(string ticker, PriceAnalyzer analyzer)
        {
            _client = new ClientWebSocket();
            _ticker = ticker;
            _priceAnalyzer = analyzer;
        }

        public async Task Main()
        {
            string socketUrl = "wss://socket.polygon.io/stocks";

            await _client.ConnectAsync(new Uri(socketUrl), CancellationToken.None);
            Debug.WriteLine("Connected to Polygon.io WebSocket.");

            string authMessage = $"{{\"action\":\"auth\",\"params\":\"{PolygonConfiguration.API_KEY}\"}}";
            await SendMessage(_client, authMessage);
            Debug.WriteLine("Authenticated with API key.");

            // Subscribe to trades
            string subscribeMessage = $"{{\"action\":\"subscribe\",\"params\":\"A.{_ticker}\"}}";
            await SendMessage(_client, subscribeMessage);

            // Continuously receive messages
            await ReceiveMessages(_client);
        }

        public async Task SendMessage(ClientWebSocket ws, string message)
        {
            byte[] buffer = Encoding.UTF8.GetBytes(message);
            await ws.SendAsync(new ArraySegment<byte>(buffer), WebSocketMessageType.Text, true, CancellationToken.None);
        }

        public async Task ReceiveMessages(ClientWebSocket ws)
        {
            byte[] buffer = new byte[1024 * 4];
            while (ws.State == WebSocketState.Open)
            {
                WebSocketReceiveResult result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                string response = Encoding.UTF8.GetString(buffer, 0, result.Count);
                //Debug.WriteLine($"Received: {response}");
                _priceAnalyzer.PriceAnalyzerMessageReceived?.Invoke(_ticker, response);
            }
        }

        public async void Close()
        {
            if (_client.State == WebSocketState.Open)
            {
                await _client.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing connection", CancellationToken.None);
            }
        }

        private ClientWebSocket _client;
        private string _ticker = string.Empty;
        public Action<string, string> OnMessageReceived;
        private PriceAnalyzer _priceAnalyzer;
    }

    public class PolygonWebSocketSimulation
    {
        public PolygonWebSocketSimulation()
        {
        }

        public Action<string, string>? OnMessageReceived;

        public async Task Main(string ticker, int multiplier, string span, DateTime start, DateTime end, string sort)
        {
            StockAggregateBars aggBars = new StockAggregateBars();
            var results = await aggBars.GetAggregateBars(ticker, multiplier, span, start, end, sort);
            foreach (var bar in results.EnumerateArray())
            {
                var data = new Dictionary<string, object> { { "o", bar.GetProperty("o") }, { "s", bar.GetProperty("t") } };

                string jsonString = JsonSerializer.Serialize(data);

                OnMessageReceived?.Invoke(ticker, jsonString);
            }
        }
    }
}
