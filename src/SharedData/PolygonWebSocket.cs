using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace Bullseye.Shared.Data
{
    public class PolygonWebSocket
    {
        public PolygonWebSocket()
        {
            _client = new ClientWebSocket();
            OnMessageReceived = new Dictionary<string, Action<JsonDocument>>();
        }

        public async Task Connect()
        {
            string socketUrl = "wss://socket.polygon.io/stocks";

            await _client.ConnectAsync(new Uri(socketUrl), CancellationToken.None);
            Console.WriteLine("Connected to Polygon.io WebSocket.");

            string authMessage = $"{{\"action\":\"auth\",\"params\":\"{PolygonConfiguration.API_KEY}\"}}";
            await SendMessage(_client, authMessage);
            Console.WriteLine("Authenticated with API key.");

            // Continuously receive messages
            await ReceiveMessages(_client);
        }

        public async Task Subscribe(string tickerString)
        {
            if (_client.State == WebSocketState.None)
            {
                _ = Connect(); // cannot await, or that awaits all messages. Just async check if we're connected below
            }

            // Aggregate tickers are in the for, but only once connected
            while (_client.State != WebSocketState.Open)
            {
                Console.WriteLine("Socket not connected, waiting 100ms");
                await Task.Delay(100);
            }
            
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
            Console.WriteLine("SendMessage: " + message);
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

                // It's better to parse here and send only messages to the handlers that need it rather then everything to everybody
                var jsonDoc = JsonDocument.Parse(response);
                var quotesArray = jsonDoc.RootElement;

                var jsonObject = quotesArray[quotesArray.GetArrayLength() - 1];

                // Get the last bid price
                if (jsonObject.GetProperty("ev").ToString() == "A")
                {
                    string ticker = jsonObject.GetProperty("sym").ToString();

                    // If the handler exists, send the message....
                    // If not, unsubscribe
                    foreach (var handler in OnMessageReceived)
                    {
                        string subscribeSymbol = $"A.{ticker}";
                        OnMessageReceived[subscribeSymbol].Invoke(jsonDoc);
                    }
                }
                else
                {
                    Console.WriteLine("Response: " + response);
                }
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
        public Dictionary<string, Action<JsonDocument>> OnMessageReceived;
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
