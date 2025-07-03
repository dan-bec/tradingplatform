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
        
        public static string AWS_ACCESS_KEY = "8020acd1-3e09-400a-a1e4-c91f9f340b53";

        public static string AWS_SECRET_KEY = "pxnJWtCbuvDAsAAxMnYlhFETkpdxxiz7";

        // REST Endpoints
        public static string TickerAggregates = "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?apiKey={API_KEY}";
    }
}
