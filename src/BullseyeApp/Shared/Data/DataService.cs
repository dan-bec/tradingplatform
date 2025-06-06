using System.Text.Json;

namespace Bullseye.Shared.Data
{
    public interface DataService
    {
        public Task<JsonDocument> GetRESTData(string url, Dictionary<string, string> param);
    }

    public class PolygonConfiguration
    {
        public static string API_KEY = "0gMEkNpzZYFLOiw8usY9x1R5IFrWSSwP";

        // REST Endpoints
        public static string TickerAggregates = "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?apiKey={API_KEY}";
    }
}
