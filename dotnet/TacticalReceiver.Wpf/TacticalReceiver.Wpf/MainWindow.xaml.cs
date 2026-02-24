using System.Collections;
using System.Collections.Concurrent;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;


namespace TacticalReceiver.Wpf;

public partial class MainWindow : Window
{
    private readonly ConcurrentDictionary<int, TrackState> _tracks = new();
    private readonly UdpReceiverService _udp;
    private readonly DispatcherTimer _uiTimer;

    private const int ListenPort = 30001;
    private const double StaleSeconds = 2.0;

    private const double WorldW = 800.0;
    private const double WorldH = 600.0;

    private int? _selectedEntityId;

    // simple “HUD-like” radar geometry
    private const double RingStep = 60.0;

    // rendering
    private readonly DrawingVisual _radarVisual = new();
    private VisualHost? _visualHost;

    public MainWindow()
    {
        InitializeComponent();

        Hud3.Text = "[H]Trail  [V]Vector  [L]Labels  [ESC]Quit";

        // Attach a visual host to the canvas (so we can draw efficiently)
        _visualHost = new VisualHost(_radarVisual);
        RadarCanvas.Children.Add(_visualHost);

        // UDP receiver
        _udp = new UdpReceiverService(ListenPort);
        _udp.MessageReceived += OnMessageReceived;
        _udp.Start();

        // UI refresh timer
        _uiTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(33) }; // ~30 FPS
        _uiTimer.Tick += UiTimer_Tick;
        _uiTimer.Start();
    }

    private void OnMessageReceived(JsonElement msg)
    {
        try
        {
            if (!msg.TryGetProperty("msg_type", out var mt) || mt.GetString() != "EntityState")
                return;

            int id = msg.GetProperty("entity_id").GetInt32();

            var tr = _tracks.GetOrAdd(id, _ => new TrackState { EntityId = id });

            tr.EntityType = msg.TryGetProperty("entity_type", out var et) ? (et.GetString() ?? tr.EntityType) : tr.EntityType;
            tr.X = msg.TryGetProperty("x", out var x) ? x.GetDouble() : tr.X;
            tr.Y = msg.TryGetProperty("y", out var y) ? y.GetDouble() : tr.Y;
            tr.HeadingDeg = msg.TryGetProperty("heading_deg", out var h) ? Wrap360(h.GetDouble()) : tr.HeadingDeg;
            tr.Speed = msg.TryGetProperty("speed", out var s) ? s.GetDouble() : tr.Speed;
            tr.Status = msg.TryGetProperty("status", out var st) ? (st.GetString() ?? tr.Status) : tr.Status;
            tr.Seq = msg.TryGetProperty("seq", out var seq) ? seq.GetInt32() : tr.Seq;
            tr.LastRxUtc = DateTime.UtcNow;

            // optional trail later
            tr.AddHistory(tr.X, tr.Y);
        }
        catch
        {
            // ignore malformed packets
        }
    }

    private void UiTimer_Tick(object? sender, EventArgs e)
    {
        var now = DateTime.UtcNow;

        var snapshot = _tracks.Values
            .OrderBy(t => t.EntityId)
            .Select(t => new TrackSnapshot(
                t.EntityId,
                t.EntityType,
                t.X,
                t.Y,
                t.HeadingDeg,
                t.Speed,
                (now - t.LastRxUtc).TotalSeconds > StaleSeconds
            ))
            .ToList();

        int total = snapshot.Count;
        int staleCount = snapshot.Count(t => t.IsStale);

        Hud1.Text = $"MODE: LIVE   PORT: {ListenPort}   ENTITIES: {total}   STALE: {staleCount}";
        Hud2.Text = $"UDP JSON EntityState";

        Footer.Text = $"TRACKS {total}/{total}   STALE=RED";

        // Update table (simple for now; optimize later if needed)
        GridTracks.ItemsSource = snapshot.Select(s => new TrackRow
        {
            EntityId = s.EntityId,
            EntityType = s.EntityType,
            X = (int)s.X,
            Y = (int)s.Y,
            Heading = ((int)s.HeadingDeg).ToString("000"),
            Speed = s.Speed.ToString("0.0"),
            State = s.IsStale ? "STALE" : "LIVE"
        }).ToList();

        DrawRadar(snapshot);
    }

    private void DrawRadar(List<TrackSnapshot> tracks)
    {
        double w = RadarCanvas.ActualWidth;
        double h = RadarCanvas.ActualHeight;
        if (w < 10 || h < 10) return;

        using var dc = _radarVisual.RenderOpen();

        // background
        dc.DrawRectangle(BrushFromRgb(5, 10, 30), null, new Rect(0, 0, w, h));

        // rings + crosshair
        double cx = w / 2.0;
        double cy = h / 2.0;

        var ringPen = new Pen(BrushFromRgb(30, 40, 70), 1);
        var crossPen = new Pen(BrushFromRgb(25, 35, 60), 1);

        double maxR = (w / 2.0) - 12;
        for (double r = RingStep; r <= maxR; r += RingStep)
            dc.DrawEllipse(null, ringPen, new Point(cx, cy), r, r);

        dc.DrawLine(crossPen, new Point(cx, 0), new Point(cx, h));
        dc.DrawLine(crossPen, new Point(0, cy), new Point(w, cy));

        foreach (var tr in tracks)
        {
            var p = WorldToRadar(tr.X, tr.Y, w, h);

            Brush dotBrush = tr.IsStale ? BrushFromRgb(255, 60, 60) : Brushes.Lime;
            Brush vecBrush = tr.IsStale ? BrushFromRgb(255, 210, 0) : Brushes.Yellow;

            dc.DrawEllipse(dotBrush, null, p, 6, 6);

            // heading vector
            double rad = tr.HeadingDeg * Math.PI / 180.0;
            double vx = Math.Sin(rad) * 16.0;
            double vy = -Math.Cos(rad) * 16.0;
            dc.DrawLine(new Pen(vecBrush, 2), p, new Point(p.X + vx, p.Y + vy));

            // label
            string label = tr.IsStale ? $"{tr.EntityId} (stale)" : tr.EntityId.ToString();
            DrawText(dc, label, p.X + 8, p.Y - 10, Colors.Gainsboro, 12);

            // selection highlight
            if (_selectedEntityId.HasValue && tr.EntityId == _selectedEntityId.Value)
            {
                var selPen = new Pen(BrushFromRgb(120, 200, 255), 1);
                dc.DrawEllipse(null, selPen, p, 12, 12);
                dc.DrawEllipse(null, selPen, p, 18, 18);
                dc.DrawLine(selPen, new Point(p.X - 10, p.Y), new Point(p.X + 10, p.Y));
                dc.DrawLine(selPen, new Point(p.X, p.Y - 10), new Point(p.X, p.Y + 10));
            }
        }
    }

    private void GridTracks_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (GridTracks.SelectedItem is TrackRow row)
            _selectedEntityId = row.EntityId;
    }

    private void Window_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape)
            Close();
    }

    private void RadarCanvas_SizeChanged(object sender, SizeChangedEventArgs e)
    {
        // force redraw on resize
        DrawRadar(_tracks.Values
            .OrderBy(t => t.EntityId)
            .Select(t =>
            {
                bool stale = (DateTime.UtcNow - t.LastRxUtc).TotalSeconds > StaleSeconds;
                return new TrackSnapshot(t.EntityId, t.EntityType, t.X, t.Y, t.HeadingDeg, t.Speed, stale);
            }).ToList());
    }

    protected override void OnClosed(EventArgs e)
    {
        _uiTimer.Stop();
        _udp.Dispose();
        base.OnClosed(e);
    }

    private static double Wrap360(double deg)
    {
        var r = deg % 360.0;
        return r < 0 ? r + 360.0 : r;
    }

    private static Point WorldToRadar(double x, double y, double radarW, double radarH)
    {
        double rx = (x / WorldW) * (radarW - 1);
        double ry = (y / WorldH) * (radarH - 1);
        return new Point(rx, ry);
    }

    private static SolidColorBrush BrushFromRgb(byte r, byte g, byte b)
    {
        var br = new SolidColorBrush(Color.FromRgb(r, g, b));
        br.Freeze();
        return br;
    }

    private static void DrawText(DrawingContext dc, string text, double x, double y, Color color, double size)
    {
        var ft = new FormattedText(
            text,
            System.Globalization.CultureInfo.InvariantCulture,
            FlowDirection.LeftToRight,
            new Typeface("Consolas"),
            size,
            new SolidColorBrush(color),
            1.0
        );
        dc.DrawText(ft, new Point(x, y));
    }



private sealed class VisualHost : FrameworkElement
{
    private readonly Visual _child;

    public VisualHost(Visual child)
    {
        _child = child ?? throw new ArgumentNullException(nameof(child));
        AddVisualChild(_child);
        AddLogicalChild(_child);
    }

    protected override int VisualChildrenCount => 1;

    protected override Visual GetVisualChild(int index)
    {
        if (index != 0) throw new ArgumentOutOfRangeException(nameof(index));
        return _child;
    }

    protected override IEnumerator LogicalChildren
    {
        get { yield return _child; }
    }
}

private record TrackSnapshot(int EntityId, string EntityType, double X, double Y, double HeadingDeg, double Speed, bool IsStale);

    private sealed class TrackRow
    {
        public int EntityId { get; set; }
        public string EntityType { get; set; } = "";
        public int X { get; set; }
        public int Y { get; set; }
        public string Heading { get; set; } = "000";
        public string Speed { get; set; } = "0.0";
        public string State { get; set; } = "";
    }
}