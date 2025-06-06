using Bullseye.Shared.Data;
using Microsoft.AspNetCore.Authorization.Infrastructure;
using Microsoft.EntityFrameworkCore.Query;
using Microsoft.Extensions.Logging.Abstractions;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.Sockets;
using System.Text.Json;

namespace Bullseye.Shared.Analyzers
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
        public string EntryPriceTrend { get; set; }
    }

    public class RealTimeTickerPriceAnalyzer
    {
        public static string UpwardTrend = "Up";
        public static string DownwardTrend = "Down";
        public static string Neutral = "Neutral";

        public static string PriceIncreaseAboveThreshold = "PriceIncreaseAboveThreshold";
        public static string PriceDecreaseAboveThreshold = "PriceDecreaseAboveThreshold";

        public Action<string, JsonDocument>? OnPriceAnalyzerMessageReceived;

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

        public void SocketMessageReceived(JsonDocument doc)
        {
            // parse the ticker, and forward to the component
            OnPriceAnalyzerMessageReceived.Invoke(Ticker, doc);
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

            // After we prune, recalculate how many times we saw increases or decreases
            // UpL30 in last 30 is really the number of times we saw jumps over our price
            // threshold in the last 30 seconds. 
            PriceIncreaseAboveThresholdLast30 = 0;
            PriceDecreaseAboveThresholdLast30 = 0;
            BelowThresholdLast30 = 0;
            foreach (var entry in _analysisQueue)
            {
                if (entry.EntryPriceTrend == PriceIncreaseAboveThreshold)
                {
                    PriceIncreaseAboveThresholdLast30++;
                }
                else if (entry.EntryPriceTrend == PriceDecreaseAboveThreshold)
                {
                    PriceDecreaseAboveThresholdLast30++;
                }
                else if (entry.EntryPriceTrend == Neutral)
                {
                    BelowThresholdLast30++;
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
                int totalIncreases = 0;
                int totalDecreases = 0;
                PriceAnalysisEntry? lastEntry = null;
                int index = 0;
                foreach (PriceAnalysisEntry entry in _analysisQueue)
                {
                    if (lastEntry == null)
                    {
                        lastEntry = entry;
                        index++;
                        continue; // cannot do anything at the first entry
                    }

                    Console.WriteLine($"[{Ticker}]: {index - 1}:{lastEntry.Price} {index}:{entry.Price} ");
                    double priceChange = (entry.Price - lastEntry.Price);
                    LastPriceChange = priceChange.ToString("F2");
                    LastPriceChangePercentage = CalculateChangePercentage(entry.Price, lastEntry.Price).ToString("F2");
                    double absoluteChange = Math.Abs(priceChange);
                    if (absoluteChange > 0.03)
                    {
                        if (priceChange < 0) // price drop
                        {
                            totalDecreases++;
                            entry.EntryPriceTrend = PriceDecreaseAboveThreshold;
                            Console.WriteLine($"[{Ticker}]Price Decrease found");
                        }
                        else if (priceChange > 0)
                        {
                            totalIncreases++;
                            entry.EntryPriceTrend = PriceIncreaseAboveThreshold;
                            Console.WriteLine($"[{Ticker}]Price Increase found");
                        }
                    }
                    else
                    {
                        entry.EntryPriceTrend = Neutral;
                    }
                    lastEntry = entry;
                    index++;
                }

                // Upward trends...
                totalIncreases = totalIncreases > 0 ? totalIncreases : 1;
                totalDecreases = totalDecreases > 0 ? totalDecreases : 1;

                double upwardTrendPercentage = (double)(totalIncreases / totalDecreases);
                Console.WriteLine($"[{Ticker}]Upward Trends: " + totalIncreases);
                Console.WriteLine($"[{Ticker}]Downward Trends: " + totalDecreases);

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
        public string LastPriceChangePercentage { get; set; }
        public Int32 UpwardTrendTotal { get; set; } = 0;
        public Int32 DownwardTrendTotal { get; set; } = 0;
        public Int32 NeutralTrendTotal { get; set; } = 0;
        public Int32 PriceIncreaseAboveThresholdLast30 { get; set; } = 0;
        public Int32 PriceDecreaseAboveThresholdLast30 { get; set; } = 0;
        public Int32 BelowThresholdLast30 { get; set; } = 0;
        public string CurrentPrice { get; set; } = string.Empty;
        public string TextStyle { get; set; } = "secondary";
    }
}
