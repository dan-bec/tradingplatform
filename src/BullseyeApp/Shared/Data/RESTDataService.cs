using System.Net.Http;
using System.Text.Json;
using static System.Net.WebRequestMethods;
using System.Diagnostics;

namespace Bullseye.Shared.Data
{
    public class RESTDataService : DataService
    {
        public RESTDataService() { }

        public async Task<JsonDocument> GetRESTData(string url, Dictionary<string, string>? parameters)
        {
            string apiKey = PolygonConfiguration.API_KEY; // Replace with your Polygon.io API key
            url += $"&apikey={apiKey}";

            using HttpClient client = new HttpClient();
            HttpResponseMessage response = await client.GetAsync(url);

            Debug.WriteLine("Url: " + url);
            if (response.IsSuccessStatusCode)
            {
                string jsonString = await response.Content.ReadAsStringAsync();
                var jsonDocument = JsonDocument.Parse(jsonString);

                Debug.WriteLine("Parsed JSON Data:");
                Debug.WriteLine(jsonDocument.RootElement);
                return jsonDocument;
            }
            else
            {
                Debug.WriteLine($"Error: {response.StatusCode}");
                return JsonDocument.Parse("");
            }
        }
    }

    public class StockAggregateBars : RESTDataService
    {
        public StockAggregateBars() { }

        public async Task<JsonElement> GetAggregateBars(string ticker, int multiplier, string span, DateTime start, DateTime end, string sort)
        {
            string startFormatted = start.ToString("yyyy-MM-dd");
            string endFormatted = end.ToString("yyyy-MM-dd");
            string url = $"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{span}/{startFormatted}/{endFormatted}?sort={sort}&limit=50000";

            var data = await GetRESTData(url, null);

            var results = data.RootElement.TryGetProperty("results", out JsonElement resultsElements);

                // Return the results
                return resultsElements;
        }
    }
}
