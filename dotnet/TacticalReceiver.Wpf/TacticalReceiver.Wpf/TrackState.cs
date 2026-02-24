using System;
using System.Collections.Generic;
using System.Windows;

namespace TacticalReceiver.Wpf;

public sealed class TrackState
{
    public int EntityId { get; set; }
    public string EntityType { get; set; } = "";

    public double X { get; set; }
    public double Y { get; set; }
    public double HeadingDeg { get; set; }
    public double Speed { get; set; }

    public string Status { get; set; } = "NO_DATA";
    public int Seq { get; set; }

    public DateTime LastRxUtc { get; set; } = DateTime.MinValue;

    // Optional trail support later
    public Queue<Point> History { get; } = new();
    public int HistoryMax { get; set; } = 25;

    public void AddHistory(double x, double y)
    {
        History.Enqueue(new Point(x, y));
        while (History.Count > HistoryMax)
            History.Dequeue();
    }
}