using System.Net.WebSockets;
using System.Text;
using System.Diagnostics;
using System.Text.Json;
using bullseye.Shared.Analyzers;
using Microsoft.AspNetCore.Mvc.ActionConstraints;

namespace bullseye.Shared.Data
{
    public class PolygonWebSocket
    {
        public PolygonWebSocket()
        {
            _client = new ClientWebSocket();
            OnMessageReceived = new Dictionary<string, Action<string>>();
        }

        public async Task Connect()
        {
            string socketUrl = "wss://socket.polygon.io/stocks";

            await _client.ConnectAsync(new Uri(socketUrl), CancellationToken.None);
            Debug.WriteLine("Connected to Polygon.io WebSocket.");

            string authMessage = $"{{\"action\":\"auth\",\"params\":\"{PolygonConfiguration.API_KEY}\"}}";
            await SendMessage(_client, authMessage);
            Debug.WriteLine("Authenticated with API key.");

            // Continuously receive messages
            await ReceiveMessages(_client);
        }

        public async Task Subscribe(string tickerString)
        {
            if (_client.State == WebSocketState.None)
            {
                await Connect();    
            }

            // Aggregate tickers are in the for
            string subscribeMessage = $"{{\"action\":\"subscribe\",\"params\":\"{tickerString}\"}}";
            await SendMessage(_client, subscribeMessage);
        }

        public async Task Unsubscribe(string tickerString)
        {
            if (_client.State == WebSocketState.None)
            {
                return; // nothing to unsubscribe for if we have not connected yet
            }
            
            // Aggregate tickers are in the for
            string subscribeMessage = $"{{\"action\":\"unsubscribe\",\"params\":\"{tickerString}\"}}";
            await SendMessage(_client, subscribeMessage);
        }

        private async Task SendMessage(ClientWebSocket ws, string message)
        {
            byte[] buffer = Encoding.UTF8.GetBytes(message);
            await ws.SendAsync(new ArraySegment<byte>(buffer), WebSocketMessageType.Text, true, CancellationToken.None);
        }

        private async Task ReceiveMessages(ClientWebSocket ws)
        {
            byte[] buffer = new byte[1024 * 4];
            while (ws.State == WebSocketState.Open)
            {
                WebSocketReceiveResult result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                string response = Encoding.UTF8.GetString(buffer, 0, result.Count);

                // parse the response
                Debug.WriteLine("Response: " + response);
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
        public Dictionary<string, Action<string>> OnMessageReceived;
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
