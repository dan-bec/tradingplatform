using System.Timers;

namespace BullseyeDesktop.Shared.Tasks
{
    public class BackgroundTaskExecutedEventArgs : EventArgs { }

    public class BackgroundTask : IDisposable
    {
        public event EventHandler<BackgroundTaskExecutedEventArgs> JobExecuted;
        void OnJobExecuted()
        {
            JobExecuted?.Invoke(this, new BackgroundTaskExecutedEventArgs());
        }

        System.Timers.Timer _Timer;
        bool _Running;

        public void StartExecuting()
        {
            if (!_Running)
            {
                // Initiate a Timer
                _Timer = new System.Timers.Timer();
                _Timer.Interval = 300_000;  // every 5 mins
                _Timer.Elapsed += HandleTimer;
                _Timer.AutoReset = true;
                _Timer.Enabled = true;

                _Running = true;
            }
        }
        void HandleTimer(object source, ElapsedEventArgs e)
        {
            // Execute required job

            // Notify any subscribers to the event
            OnJobExecuted();
        }
        public void Dispose()
        {
            if (_Running)
            {
                // Clear up the timer
            }
        }
    }
}
