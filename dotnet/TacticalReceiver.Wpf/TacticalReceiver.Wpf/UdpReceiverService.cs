using System;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace TacticalReceiver.Wpf;

public sealed class UdpReceiverService : IDisposable
{
    private readonly UdpClient _udp;
    private CancellationTokenSource? _cts;
    private Task? _task;

    public event Action<JsonElement>? MessageReceived;

    public UdpReceiverService(int port)
    {
        _udp = new UdpClient(port);
    }

    public void Start()
    {
        if (_cts != null) return;
        _cts = new CancellationTokenSource();
        _task = Task.Run(() => ReceiveLoop(_cts.Token));
    }

    private async Task ReceiveLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var res = await _udp.ReceiveAsync(ct);
                var json = Encoding.UTF8.GetString(res.Buffer);

                using var doc = JsonDocument.Parse(json);
                MessageReceived?.Invoke(doc.RootElement.Clone());
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch
            {
                // swallow malformed packets/transient errors
            }
        }
    }

    public void Stop()
    {
        if (_cts == null) return;
        _cts.Cancel();
        try { _task?.Wait(250); } catch { }
        _cts.Dispose();
        _cts = null;
        _task = null;
    }

    public void Dispose()
    {
        Stop();
        _udp.Dispose();
    }
}