using bullseye.Shared.Data;
using Microsoft.AspNetCore.Authorization.Infrastructure;
using Microsoft.EntityFrameworkCore.Query;
using Microsoft.Extensions.Logging.Abstractions;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.Sockets;

namespace bullseye.Shared.Analyzers
{
    public class PriceAnalysisEntry
    {
        public PriceAnalysisEntry()
        {

        }

        public PriceAnalysisEntry(double price, DateTime timestamp)
        {
            Price = price;
            Timestamp = timestamp;
        }

        public double Price { get; }
        public DateTime Timestamp { get; }
        public string Trend { get; set; }
    }

    public class RealTimeTickerPriceAnalyzer
    {
        public static string UpwardTrend = "Up";
        public static string DownwardTrend = "Down";
        public static string Neutral = "Neutral";

        public Action<string, string>? OnPriceAnalyzerMessageReceived;

        // Creates a new price analyzer following real-time stock trades
        // Each trade comes in with a timestamp, but the UX will only call this approx every second
        // 
        public RealTimeTickerPriceAnalyzer(string ticker, int totalLookbackSeconds, PolygonWebSocket socket) 
        {
            Ticker = ticker;
            _totalLookbackSeconds = totalLookbackSeconds;
            _analysisQueue = new ConcurrentQueue<PriceAnalysisEntry>();
            _start = DateTime.Now;
            _subscribeString = $"A.{ticker}";

            _socket = socket;
        }

        public async Task SubscribeToSocket()
        {
            // before we subscribe, add our socket message received handler
            // this is not the handler that invokes the component, that's setup through the component itself
            _socket.OnMessageReceived[_subscribeString] = SocketMessageReceived;
            await _socket.Subscribe(_subscribeString);
        }

        public void SocketMessageReceived(string msg)
        {
            // parse the ticker, and forward to the component
            OnPriceAnalyzerMessageReceived.Invoke(Ticker, msg);
        }

        public void AddPrice(double price, DateTime timestamp)
        {
            // Is this price at least a second different than the last one?
            if (_analysisQueue.Count > 0)
            {
                DateTime lastTimeStamp = _analysisQueue.Last().Timestamp;
                double lastPrice = _analysisQueue.Last().Price;
                TimeSpan difference = timestamp - lastTimeStamp;

                if (difference.TotalSeconds >= 1)
                {
                    //Debug.WriteLine("Current Price " + price + " is at least 1 second from our last stored " + lastPrice);
                    _analysisQueue.Enqueue(new PriceAnalysisEntry(price, timestamp));
                }
            }
            else
            {
                _analysisQueue.Enqueue(new PriceAnalysisEntry(price, timestamp));
            }

            PruneQueue();
        }

        private void PruneQueue()
        {
            if (_analysisQueue.Count <= _totalLookbackSeconds)
            {
                // nothing to do, need at least total lookback to prune
                return;
            }

            // Can only prune if we have over our lookback amount
            while (_analysisQueue.Count > _totalLookbackSeconds)
            {
                _ = _analysisQueue.TryDequeue(out _);
            }

            if (_analysisQueue.Count != _totalLookbackSeconds)
            {
                throw new Exception("Queue size is not correct");
            }

            // After we prune, we recalculate the last 30 seconds trends totals
            UpwardTrendLast30 = 0;
            DownwardTrendLast30 = 0;
            NeutralTrendLast30 = 0;
            foreach (var entry in _analysisQueue)
            {
                if (entry.Trend == UpwardTrend)
                {
                    UpwardTrendLast30++;
                }
                else if (entry.Trend == DownwardTrend)
                {
                    DownwardTrendLast30++;
                }
                else
                {
                    NeutralTrendLast30++;
                }
            }
        }

        private static double CalculateChangePercentage(double oldPrice, double newPrice)
        {
            if (oldPrice == 0)
            {
                throw new ArgumentException("Old price cannot be zero.");
            }

            return ((newPrice - oldPrice) / Math.Abs(oldPrice)) * 100;
        }

        public string GetTrend()
        {
            // We must have at least 30 data points to build a trend
            if (_analysisQueue.Count == _totalLookbackSeconds)
            {
                Debug.WriteLine("Gathering Trend");
                int totalIncreases = 0;
                int totalDecreases = 0;
                PriceAnalysisEntry? lastEntry = null;
                foreach (PriceAnalysisEntry entry in _analysisQueue)
                {
                    if (lastEntry == null)
                    {
                        lastEntry = entry;
                        continue; // cannot do anything with a single entry
                    }

                    double priceChange = (entry.Price - lastEntry.Price);
                    LastPriceChange = priceChange.ToString();
                    LastPriceChangePercentage = CalculateChangePercentage(entry.Price, lastEntry.Price);
                    double absoluteChange = Math.Abs(priceChange);
                    if (absoluteChange > 0.03)
                    {
                        if (priceChange < 0) // price drop
                        {
                            totalDecreases++;
                            entry.Trend = DownwardTrend;
                            Debug.WriteLine("Price Decrease found");
                        }
                        else if (priceChange > 0)
                        {
                            totalIncreases++;
                            entry.Trend = UpwardTrend;
                            Debug.WriteLine("Price Increase found");
                        }
                    }
                    else
                    {
                        entry.Trend = Neutral;
                    }
                    lastEntry = entry;
                }

                // Upward trends...
                totalIncreases = totalIncreases > 0 ? totalIncreases : 1;
                totalDecreases = totalDecreases > 0 ? totalDecreases : 1;

                double upwardTrendPercentage = (double)(totalIncreases / totalDecreases);
                Debug.WriteLine("Upward Trends: " + totalIncreases);
                Debug.WriteLine("Downward Trends: " + totalDecreases);

                if (upwardTrendPercentage > 2.5) // upward trend
                {
                    UpwardTrendTotal++;
                    return UpwardTrend;
                }

                double downwardTrendPercentage = (double)(totalDecreases / totalIncreases);
                    
                if (downwardTrendPercentage < 2.5) // downward trend
                {
                    DownwardTrendTotal++;
                    return DownwardTrend;
                }
                NeutralTrendTotal++;
            }
            return Neutral;
        }

        public async Task Close()
        {
            _socket.OnMessageReceived.Remove(_subscribeString);
            await _socket.Unsubscribe(_subscribeString);
        }

        public string Ticker { get; } = String.Empty;
        private string _subscribeString = String.Empty;
        private ConcurrentQueue<PriceAnalysisEntry> _analysisQueue;
        private int _totalLookbackSeconds;
        private DateTime _start;
        private readonly PolygonWebSocket _socket;
        public string LastPriceChange { get; set;  } = string.Empty;
        public double LastPriceChangePercentage { get; set; }
        public Int32 UpwardTrendTotal { get; set; } = 0;
        public Int32 DownwardTrendTotal { get; set; } = 0;
        public Int32 NeutralTrendTotal { get; set; } = 0;
        public Int32 UpwardTrendLast30 { get; set; } = 0;
        public Int32 DownwardTrendLast30 { get; set; } = 0;
        public Int32 NeutralTrendLast30 { get; set; } = 0;
        public string CurrentPrice { get; set; } = string.Empty;
        public string TextStyle { get; set; } = "secondary";
    }
}
