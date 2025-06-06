namespace bullseye.Shared.Data
{
    public class PolygonDataModel
    {
    }

    public class StockBar
    {
        public decimal C { get; set; } // Close price
        public decimal H { get; set; } // High price
        public decimal L { get; set; } // Low price
        public decimal O { get; set; } // Open price
        public long T { get; set; } // Timestamp
        public long V { get; set; } // Volume
    }

    public class StockAggregateBarResponse
    {
        public string? Ticker { get; set; }
        public List<StockBar>? Results { get; set; }
    }
}
