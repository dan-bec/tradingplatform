namespace BullseyeApp.Shared.Configuration
{
    public static class MarketHours
    {
        public static readonly TimeSpan OpenTime = new TimeSpan(14, 30, 0); // 2:30 PM UTC
        public static readonly TimeSpan CloseTime = new TimeSpan(21, 0, 0); // 9:00 PM UTC
    }
}
