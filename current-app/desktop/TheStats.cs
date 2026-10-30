// Dedicated presentation window. INTERLINKED alone owns the Stats backend and library lock.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace TheStatsDesktop
{
    internal static class Guard
    {
        internal const string Kit = @"C:\Users\Jude\Documents\MSI-Project-Library";
        internal const string Source = @"C:\Users\Jude\Documents\Codex\The-Stats\current-app";
        internal const string User = @"C:\Users\Jude";
        internal static readonly string InstalledDesktop = Path.Combine(Kit, @"INTERLINKED-Desktop\INTERLINKED.exe");
        internal static void Need(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
        internal static bool SamePath(string left, string right)
        { return String.Equals(Path.GetFullPath(left).TrimEnd('\\'), Path.GetFullPath(right).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase); }
        internal static void Ordinary(string path)
        {
            Need(!path.StartsWith(@"\\") && Path.IsPathRooted(path), "Use an ordinary local path.");
            string current = Path.GetFullPath(path);
            while (current != null)
            {
                try { Need(((long)File.GetAttributes(current) & 0x441400) == 0, "Link, offline or cloud-placeholder paths are not supported."); }
                catch (FileNotFoundException) { }
                catch (DirectoryNotFoundException) { }
                current = Path.GetDirectoryName(current);
            }
        }
        internal static Dictionary<string, object> ReadJson(string path)
        {
            Ordinary(path);
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                Need(stream.Length <= 16384, "Connection metadata is too large.");
                using (var reader = new StreamReader(stream, new UTF8Encoding(false, true)))
                {
                    var result = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 12 }.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                    Need(result != null, "Connection metadata is unavailable."); return result;
                }
            }
        }
        internal static string Text(Dictionary<string, object> value, string key)
        { object result; Need(value.TryGetValue(key, out result) && result is string, "Required connection metadata is missing."); return (string)result; }
        internal static int Number(Dictionary<string, object> value, string key)
        { object result; Need(value.TryGetValue(key, out result) && result is int, "Required connection number is missing."); return (int)result; }
        internal static string Digest(string path)
        {
            Ordinary(path);
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        internal static void Pin(string path, string expected)
        { Need(Regex.IsMatch(expected, "^[a-f0-9]{64}$") && Digest(path) == expected, "The reviewed Stats runtime changed. Review its INTERLINKED connection before opening it."); }
        internal static void NewFixture(string path)
        {
            Ordinary(path);
            string full = Path.GetFullPath(path).TrimEnd('\\') + "\\";
            foreach (string protectedRoot in new[] { Kit, Path.GetDirectoryName(Source), Path.Combine(User, @"AppData\Local\ProjectLibrary") })
                Need(!full.StartsWith(protectedRoot.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase), "Fixtures must be separate from the application, installed kit and managed cache.");
            Need(!Directory.Exists(path) && !File.Exists(path), "Use a new fixture directory; existing contents are preserved.");
            Directory.CreateDirectory(path);
        }
        internal static void Receipt(string path, object value)
        { File.WriteAllText(path, new JavaScriptSerializer().Serialize(value), new UTF8Encoding(false)); }
        internal static void Observe(Task task)
        { task.ContinueWith(delegate(Task failed) { var observed = failed.Exception; }, TaskContinuationOptions.OnlyOnFaulted); }
    }

    internal sealed class Options
    {
        internal bool Preview, Smoke, SelfTest;
        internal string Fixture;
        internal static Options Parse(string[] args)
        {
            var result = new Options();
            if (args.Length == 0) return result;
            if (args.Length == 2 && args[0] == "--self-test") { result.SelfTest = true; result.Fixture = Path.GetFullPath(args[1]); return result; }
            Guard.Need(args.Length >= 3 && args[0] == "--preview" && args[1] == "--fixture-directory", "Production accepts no paths or addresses. Preview requires --preview --fixture-directory <new local directory>.");
            result.Preview = true; result.Fixture = Path.GetFullPath(args[2]);
            Guard.Need(args.Length == 3 || (args.Length == 4 && args[3] == "--smoke-test"), "Unknown preview option.");
            result.Smoke = args.Length == 4; return result;
        }
    }

    internal static class Policy
    {
        internal static bool Local(string value, Uri origin)
        {
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri) && uri.Scheme == "http" && uri.UserInfo == "" &&
                uri.Host == "127.0.0.1" && uri.Port == origin.Port && uri.GetLeftPart(UriPartial.Authority) == origin.GetLeftPart(UriPartial.Authority);
        }
        internal static bool Resource(string value, Uri origin)
        {
            if (Local(value, origin) || value.StartsWith("blob:" + origin.GetLeftPart(UriPartial.Authority) + "/", StringComparison.Ordinal)) return true;
            if (value.StartsWith("data:image/", StringComparison.Ordinal) || value.StartsWith("data:font/", StringComparison.Ordinal)) return true;
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri) && uri.Scheme == "ws" && uri.Host == "127.0.0.1" &&
                uri.Port == origin.Port && uri.UserInfo == "" && uri.AbsolutePath.StartsWith("/_stcore/", StringComparison.Ordinal);
        }
        internal static bool External(string value)
        {
            Uri uri; IPAddress address;
            if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || uri.Scheme != "https" || !uri.IsDefaultPort ||
                uri.UserInfo != "" || uri.IsLoopback || IPAddress.TryParse(uri.Host, out address) || !uri.Host.Contains(".")) return false;
            string query, fragment;
            try { query = Uri.UnescapeDataString(uri.Query); fragment = Uri.UnescapeDataString(uri.Fragment); } catch (UriFormatException) { return false; }
            if (fragment != "" && (!Regex.IsMatch(fragment, "^#[A-Za-z][A-Za-z0-9_.:-]{0,119}$") || Regex.IsMatch(fragment, "token|auth|secret|password|credential|signature|session", RegexOptions.IgnoreCase))) return false;
            return !Regex.IsMatch(query, @"(?:[?&])(?:[^=&]*(?:token|auth|secret|password|credential|signature|session|api.?key|access.?key)[^=&]*|code|key)=", RegexOptions.IgnoreCase);
        }
        internal static bool Download(string value, string name, Uri origin)
        {
            bool source = value.StartsWith("blob:" + origin.GetLeftPart(UriPartial.Authority) + "/", StringComparison.Ordinal);
            Uri uri;
            if (Local(value, origin) && Uri.TryCreate(value, UriKind.Absolute, out uri))
                source = uri.AbsolutePath.StartsWith("/media/", StringComparison.Ordinal) || uri.AbsolutePath.StartsWith("/_stcore/download/", StringComparison.Ordinal) || uri.AbsolutePath == "/download/fixture.csv";
            return source && Regex.IsMatch(Path.GetExtension(name), "^\\.(csv|tsv|json|html|md|txt|png|pdf|zip|xlsx)$", RegexOptions.IgnoreCase);
        }
    }

    internal sealed class ProcessIdentity
    {
        internal string Executable;
        internal DateTimeOffset Started;
        internal bool Alive;
    }

    internal sealed class Connection
    {
        internal Uri Origin;
        internal int Pid;
        internal string Python;
        internal DateTimeOffset JournalTime;
        internal static Connection Validate(Dictionary<string, object> owner, Dictionary<string, object> config,
            Dictionary<string, object> session, string expectedSource, Func<int, ProcessIdentity> process)
        {
            Guard.Need(owner.Count == 3 && Guard.Text(owner, "format") == "interlinked-stats-owner-v1" &&
                Guard.SamePath(Guard.Text(owner, "kit"), Guard.Kit) && owner.ContainsKey("demo") && owner["demo"] is bool && !(bool)owner["demo"], "The Stats connection belongs to another installation.");
            Guard.Need(config.Count == 7 && Guard.Text(config, "format") == "interlinked-stats-connection-v1", "Unsupported reviewed Stats connection.");
            string source = Guard.Text(config, "sourceRoot"), python = Guard.Text(config, "python");
            Guard.Need(Guard.SamePath(source, expectedSource) && Guard.SamePath(python, Path.Combine(source, @".venv\Scripts\python.exe")), "The reviewed Stats source or interpreter differs.");
            int port = Guard.Number(config, "port"); Guard.Need(port >= 1024 && port <= 65535, "Invalid reviewed Stats port.");
            Guard.Need(Guard.Text(session, "format") == "interlinked-stats-session-v1" && Guard.Text(session, "projectId") == "stats-active" && Guard.Text(session, "status") == "RUNNING", "The Stats is not running.");
            int pid = Guard.Number(session, "pid"); Guard.Need(pid > 0, "The managed Stats process is unavailable.");
            DateTimeOffset written;
            Guard.Need(DateTimeOffset.TryParse(Guard.Text(session, "utc"), out written), "The managed session timestamp is invalid.");
            var identity = process(pid);
            Guard.Need(identity.Alive && Guard.SamePath(identity.Executable, python) && identity.Started <= written.AddSeconds(2) &&
                identity.Started >= written.AddMinutes(-2), "The managed Stats session no longer identifies its reviewed process. Recheck INTERLINKED.");
            return new Connection { Origin = new Uri("http://127.0.0.1:" + port + "/"), Pid = pid, Python = python, JournalTime = written };
        }
        internal static Connection Production()
        {
            Guard.Need(String.Equals(Environment.MachineName, "THIS-MACHINE", StringComparison.OrdinalIgnoreCase) &&
                Guard.SamePath(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), Guard.User), "Use the reviewed The Stats connection on THIS-MACHINE as Jude.");
            string root = Path.Combine(Guard.Kit, @"INTERLINKED-GUI-State\stats");
            var config = Guard.ReadJson(Path.Combine(root, "connection.json"));
            var result = Validate(Guard.ReadJson(Path.Combine(root, "OWNER.json")), config, Guard.ReadJson(Path.Combine(root, "session.json")), Guard.Source,
                delegate(int pid)
                {
                    using (var process = Process.GetProcessById(pid))
                        return new ProcessIdentity { Alive = !process.HasExited, Executable = process.MainModule.FileName, Started = new DateTimeOffset(process.StartTime.ToUniversalTime()) };
                });
            Guard.Pin(Path.Combine(Guard.Source, @"scripts\launch.py"), Guard.Text(config, "launcherSha256"));
            Guard.Pin(result.Python, Guard.Text(config, "pythonSha256"));
            Guard.Pin(Path.Combine(Guard.Source, "requirements.lock.txt"), Guard.Text(config, "lockSha256"));
            return result;
        }
        internal static async Task Healthy(Uri origin)
        {
            using (var handler = new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
            using (var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(3) })
                await Healthy(client, origin, 3000);
        }
        internal static async Task Healthy(HttpClient client, Uri origin, int timeoutMilliseconds)
        {
            using (var cancellation = new CancellationTokenSource())
            {
                var operation = ReadHealth(client, origin, cancellation.Token);
                if (await Task.WhenAny(operation, Task.Delay(timeoutMilliseconds)) != operation)
                {
                    cancellation.Cancel(); client.CancelPendingRequests();
                    Guard.Observe(operation);
                    throw new TimeoutException("The Stats readiness check timed out. Check its status in INTERLINKED.");
                }
                await operation;
            }
        }
        private static async Task ReadHealth(HttpClient client, Uri origin, CancellationToken cancellation)
        {
            using (var response = await client.GetAsync(new Uri(origin, "_stcore/health"), HttpCompletionOption.ResponseHeadersRead, cancellation))
            {
                Guard.Need(response.StatusCode == HttpStatusCode.OK, "The Stats is not ready. Check its status in INTERLINKED.");
                using (var stream = await response.Content.ReadAsStreamAsync())
                {
                    var bytes = new byte[65]; int count = 0, read;
                    while (count < bytes.Length && (read = await stream.ReadAsync(bytes, count, bytes.Length - count, cancellation)) > 0) count += read;
                    Guard.Need(count <= 64 && Encoding.UTF8.GetString(bytes, 0, count).Trim() == "ok", "The Stats readiness response was unexpected.");
                }
            }
        }
    }

    internal sealed class PreviewServer : IDisposable
    {
        private readonly TcpListener listener = new TcpListener(IPAddress.Loopback, 0);
        private bool closed;
        internal readonly Uri Origin;
        internal PreviewServer()
        {
            listener.Start(); Origin = new Uri("http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port + "/");
            Guard.Observe(Task.Run((Func<Task>)Serve));
        }
        private async Task Serve()
        {
            while (!closed)
            {
                TcpClient client;
                try { client = await listener.AcceptTcpClientAsync(); } catch (ObjectDisposedException) { break; } catch (SocketException) { break; }
                Guard.Observe(Task.Run(async delegate
                {
                    using (client)
                    using (var stream = client.GetStream())
                    {
                        try
                        {
                            client.ReceiveTimeout = 3000;
                            var data = new List<byte>(); var one = new byte[1];
                            while (data.Count < 8192 && await stream.ReadAsync(one, 0, 1) > 0)
                            { data.Add(one[0]); int n = data.Count; if (n >= 4 && data[n - 4] == 13 && data[n - 3] == 10 && data[n - 2] == 13 && data[n - 1] == 10) break; }
                            string request = Encoding.ASCII.GetString(data.ToArray()).Split('\n')[0];
                            string route = request.Split(' ').Length > 1 ? request.Split(' ')[1] : "/";
                            string body = route == "/_stcore/health" ? "ok" : Html(route == "/next");
                            byte[] bytes = Encoding.UTF8.GetBytes(body);
                            string header = "HTTP/1.1 200 OK\r\nContent-Type: " + (route == "/_stcore/health" ? "text/plain" : "text/html; charset=utf-8") + "\r\nContent-Length: " + bytes.Length + "\r\nConnection: close\r\n\r\n";
                            byte[] headers = Encoding.ASCII.GetBytes(header); await stream.WriteAsync(headers, 0, headers.Length); await stream.WriteAsync(bytes, 0, bytes.Length);
                        }
                        catch (IOException) { } catch (ObjectDisposedException) { }
                    }
                }));
            }
        }
        private static string Html(bool next)
        {
            return "<!doctype html><html><meta charset='utf-8'><title>The Stats preview</title><style>body{margin:0;background:#090909;color:#eee;font:16px Segoe UI,sans-serif}main{max-width:1020px;margin:64px auto;padding:0 40px}small{font:12px Consolas;letter-spacing:.2em;color:#aaa}h1{font-size:64px;letter-spacing:-.05em;margin:20px 0}p{line-height:1.7;color:#bbb}.cards{display:flex;gap:16px;margin:42px 0}.card{border:1px solid #444;flex:1;padding:25px;background:#111}.card b{display:block;font:42px Consolas;margin-top:14px}a{color:#fff}hr{border:0;border-top:1px solid #333}</style><main data-fixture='the-stats-preview'><small>[REDACTED] / THE STATS / SYNTHETIC PREVIEW</small><h1>Read the signal.</h1><p>A dedicated home for the band's music and social evidence.</p><hr><p>Selected analysis: <strong>synthetic-preview-only</strong><br>No existing library is opened in this preview.</p><div class='cards'><div class='card'>Streams<b>4,246</b></div><div class='card'>Listeners<b>1,062</b></div><div class='card'>Followers<b>+28</b></div></div><p>Illustrative fixture values · not a report about the band.</p><a href='/next'>" + (next ? "Local navigation verified" : "Inspect the fixture") + "</a></main></html>";
        }
        public void Dispose() { closed = true; listener.Stop(); }
    }

    internal sealed class StatsWindow : Form
    {
        private readonly Options options;
        private readonly Label status = new Label();
        private readonly Panel body = new Panel();
        private readonly Button reload = new Button();
        private readonly System.Windows.Forms.Timer monitor = new System.Windows.Forms.Timer();
        private readonly TableLayoutPanel brandHeader = new TableLayoutPanel();
        private readonly PictureBox brandLogo = new PictureBox();
        private readonly Label brandTitle = new Label();
        private readonly Label brandTagline = new Label();
        private readonly FlowLayoutPanel brandControls = new FlowLayoutPanel();
        private WebView2 view;
        private PreviewServer preview;
        private Connection connection;
        private Uri origin;
        private bool loading, checking, smokeRunning, disposed;
        private int blocked;
        private readonly string profile;
        private readonly Dictionary<string, object> checks = new Dictionary<string, object>();
        internal int ExitCode;
        internal StatsWindow(Options value)
        {
            options = value; Text = "The Stats — [REDACTED]"; Width = 1440; Height = 960; MinimumSize = new Size(980, 700);
            StartPosition = FormStartPosition.CenterScreen; BackColor = Color.FromArgb(9, 9, 9); ForeColor = Color.White;
            Font = new Font("Segoe UI", 10); AutoScaleMode = AutoScaleMode.Dpi;
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            brandHeader.Dock = DockStyle.Top; brandHeader.Height = 104;
            brandHeader.Padding = new Padding(24, 14, 22, 14); brandHeader.BackColor = Color.FromArgb(13, 13, 13);
            brandHeader.ColumnCount = 3; brandHeader.RowCount = 1;
            brandHeader.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 126));
            brandHeader.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            brandHeader.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 340));
            brandHeader.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            string logo = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "couch-sticker-original.png");
            brandLogo.Dock = DockStyle.Fill; brandLogo.Margin = Padding.Empty;
            brandLogo.SizeMode = PictureBoxSizeMode.Zoom; brandLogo.BackColor = brandHeader.BackColor;
            if (File.Exists(logo)) brandLogo.Image = Image.FromFile(logo);
            var titles = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2, Margin = new Padding(24, 0, 12, 0), Padding = Padding.Empty };
            titles.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            titles.RowStyles.Add(new RowStyle(SizeType.Percent, 55)); titles.RowStyles.Add(new RowStyle(SizeType.Percent, 45));
            brandTitle.Dock = DockStyle.Fill; brandTitle.Margin = Padding.Empty; brandTitle.Text = "THE STATS";
            brandTitle.Font = new Font("Consolas", 17, FontStyle.Bold); brandTitle.TextAlign = ContentAlignment.MiddleLeft; brandTitle.AutoEllipsis = true;
            brandTagline.Dock = DockStyle.Fill; brandTagline.Margin = Padding.Empty; brandTagline.Text = "[REDACTED] / MUSIC + SOCIAL SIGNAL";
            brandTagline.Font = new Font("Consolas", 10); brandTagline.TextAlign = ContentAlignment.MiddleLeft; brandTagline.ForeColor = Color.Silver; brandTagline.AutoEllipsis = true;
            titles.Controls.Add(brandTitle, 0, 0); titles.Controls.Add(brandTagline, 0, 1);
            brandControls.Dock = DockStyle.Fill; brandControls.Margin = Padding.Empty;
            brandControls.FlowDirection = FlowDirection.LeftToRight; brandControls.WrapContents = false; brandControls.Padding = new Padding(0, 18, 0, 0);
            reload.Text = "Reload"; Style(reload, 100); reload.Click += async delegate { await Connect(); };
            var interlinked = new Button { Text = "Open INTERLINKED" }; Style(interlinked, 205);
            interlinked.Click += delegate
            {
                if (options.Preview) { status.Text = "Preview only · the installed INTERLINKED controls are not opened by this fixture."; return; }
                try { Guard.Ordinary(Guard.InstalledDesktop); Process.Start(new ProcessStartInfo(Guard.InstalledDesktop) { UseShellExecute = true }); }
                catch (Exception) { status.Text = "INTERLINKED could not open. Use its installed shortcut to manage The Stats."; }
            };
            brandControls.Controls.Add(reload); brandControls.Controls.Add(interlinked);
            brandHeader.Controls.Add(brandLogo, 0, 0); brandHeader.Controls.Add(titles, 1, 0); brandHeader.Controls.Add(brandControls, 2, 0);
            status.Dock = DockStyle.Bottom; status.Height = 39; status.Padding = new Padding(22, 0, 8, 0); status.TextAlign = ContentAlignment.MiddleLeft;
            status.Font = new Font("Segoe UI", 9); status.ForeColor = Color.Silver; status.BackColor = Color.FromArgb(16, 16, 16);
            body.Dock = DockStyle.Fill; Controls.Add(body); Controls.Add(status); Controls.Add(brandHeader);
            if (options.Preview) { preview = new PreviewServer(); origin = preview.Origin; profile = Path.Combine(options.Fixture, "WebView2"); }
            else profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TheStatsDesktop", "WebView2");
            Shown += async delegate { await Connect(); };
            monitor.Interval = 10000; monitor.Tick += async delegate { await CheckSession(); }; monitor.Start();
            FormClosed += delegate { disposed = true; monitor.Stop(); monitor.Dispose(); if (view != null) view.Dispose(); if (preview != null) preview.Dispose(); };
        }
        private static void Style(Button button, int width)
        { button.Width = width; button.Height = 39; button.FlatStyle = FlatStyle.Flat; button.FlatAppearance.BorderColor = Color.FromArgb(90, 90, 90); button.BackColor = Color.FromArgb(20, 20, 20); button.ForeColor = Color.White; button.Margin = new Padding(6, 0, 6, 0); }
        internal static string FailureCopy(string message)
        {
            if (message == "The Stats is not running.")
                return "Start The Stats in INTERLINKED, then choose Reload.\r\n\r\nYour existing library stays in its managed location.";
            return message + "\r\n\r\nOpen INTERLINKED to check The Stats, then choose Reload.\r\nYour existing library stays in its managed location.";
        }
        private bool HeaderFits(int width)
        {
            Width = width; PerformLayout(); brandHeader.PerformLayout();
            Rectangle logo = RectangleToClient(brandLogo.RectangleToScreen(brandLogo.ClientRectangle));
            Rectangle title = RectangleToClient(brandTitle.RectangleToScreen(brandTitle.ClientRectangle));
            Rectangle tagline = RectangleToClient(brandTagline.RectangleToScreen(brandTagline.ClientRectangle));
            Rectangle controls = RectangleToClient(brandControls.RectangleToScreen(brandControls.ClientRectangle));
            bool textFits = true;
            foreach (var label in new[] { brandTitle, brandTagline })
                using (var drawing = label.CreateGraphics())
                {
                    Size measured = TextRenderer.MeasureText(drawing, label.Text, label.Font, new Size(Int32.MaxValue, Int32.MaxValue), TextFormatFlags.SingleLine | TextFormatFlags.NoPadding);
                    textFits &= measured.Width + 4 <= label.ClientSize.Width && measured.Height <= label.ClientSize.Height;
                }
            return brandLogo.Image != null && logo.Right <= title.Left && logo.Right <= tagline.Left && title.Right <= controls.Left &&
                tagline.Right <= controls.Left && title.Bottom <= tagline.Top && brandControls.ClientRectangle.Contains(brandControls.Controls[1].Bounds) && textFits;
        }
        internal void ActivateWindow() { if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal; Show(); Activate(); }
        private void Failure(string message)
        {
            if (disposed) return;
            if (view != null) { body.Controls.Remove(view); view.Dispose(); view = null; }
            body.Controls.Clear();
            var text = new Label { Dock = DockStyle.Fill, Padding = new Padding(64), TextAlign = ContentAlignment.MiddleCenter, ForeColor = Color.White, Font = new Font("Segoe UI", 16), Text = FailureCopy(message) };
            body.Controls.Add(text); status.Text = "Waiting for The Stats · closing this window leaves INTERLINKED and its library untouched.";
        }
        private async Task Connect()
        {
            if (loading || disposed) return; loading = true; reload.Enabled = false;
            try
            {
                status.Text = "Opening The Stats…";
                CoreWebView2Environment.GetAvailableBrowserVersionString();
                if (!options.Preview) { connection = Connection.Production(); origin = connection.Origin; }
                await Connection.Healthy(origin);
                if (!options.Preview) { var recheck = Connection.Production(); Guard.Need(recheck.Pid == connection.Pid && recheck.JournalTime == connection.JournalTime, "The managed session changed while opening. Choose Reload."); }
                if (disposed) return;
                if (view != null) { body.Controls.Remove(view); view.Dispose(); }
                body.Controls.Clear(); Guard.Ordinary(profile);
                var environment = await CoreWebView2Environment.CreateAsync(null, profile, null);
                var privateOptions = environment.CreateCoreWebView2ControllerOptions(); privateOptions.IsInPrivateModeEnabled = true;
                view = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor }; body.Controls.Add(view);
                await view.EnsureCoreWebView2Async(environment, privateOptions); Configure();
                view.CoreWebView2.NavigationCompleted += async delegate(object sender, CoreWebView2NavigationCompletedEventArgs args)
                {
                    if (args.IsSuccess)
                    {
                        status.Text = options.Preview ? "Preview · synthetic values · no existing library is opened." : "Connected · INTERLINKED protects your library. Closing this window keeps The Stats running.";
                        if (options.Smoke && !smokeRunning) { smokeRunning = true; await Smoke(); }
                    }
                    else if (options.Smoke && !smokeRunning) { FinishSmoke(false, "Preview navigation failed."); }
                };
                view.CoreWebView2.Navigate(origin.AbsoluteUri);
            }
            catch (Exception error)
            {
                Failure(error is WebView2RuntimeNotFoundException ? "Microsoft WebView2 Runtime is unavailable." : error.Message);
                if (options.Smoke) FinishSmoke(false, error.GetType().Name + ": " + error.Message);
            }
            finally { loading = false; if (!disposed) reload.Enabled = true; }
        }
        private async Task CheckSession()
        {
            if (options.Preview || loading || checking || disposed || view == null) return;
            checking = true;
            try { var current = Connection.Production(); Guard.Need(connection != null && current.Pid == connection.Pid && current.JournalTime == connection.JournalTime, "The managed Stats session changed. Choose Reload to reconnect."); await Connection.Healthy(current.Origin); }
            catch (Exception) { Failure("The managed Stats session is no longer ready."); }
            finally { checking = false; }
        }
        private void Configure()
        {
            var core = view.CoreWebView2;
            core.Settings.AreDevToolsEnabled = false; core.Settings.AreHostObjectsAllowed = false; core.Settings.IsWebMessageEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = false; core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsPasswordAutosaveEnabled = false; core.Settings.IsGeneralAutofillEnabled = false;
            core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs args) { args.State = CoreWebView2PermissionState.Deny; };
            core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs args)
            {
                if (Policy.Local(args.Uri, origin)) return;
                args.Cancel = true; blocked++;
                if (args.IsUserInitiated) External(args.Uri);
            };
            core.FrameNavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs args)
            { if (args.Uri != "about:blank" && args.Uri != "about:srcdoc" && !Policy.Local(args.Uri, origin)) args.Cancel = true; };
            core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += delegate(object sender, CoreWebView2WebResourceRequestedEventArgs args)
            { if (!Policy.Resource(args.Request.Uri, origin)) args.Response = core.Environment.CreateWebResourceResponse(new MemoryStream(), 403, "Blocked", "Content-Type: text/plain"); };
            core.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs args)
            { args.Handled = true; if (Policy.Local(args.Uri, origin)) core.Navigate(args.Uri); else if (args.IsUserInitiated) External(args.Uri); };
            core.DownloadStarting += delegate(object sender, CoreWebView2DownloadStartingEventArgs args)
            {
                args.Handled = true; string name = Path.GetFileName(args.ResultFilePath);
                if (options.Preview || !Policy.Download(args.DownloadOperation.Uri, name, origin)) { args.Cancel = true; return; }
                using (var dialog = new SaveFileDialog { FileName = name, Filter = "The Stats exports|*.csv;*.tsv;*.json;*.html;*.md;*.txt;*.png;*.pdf;*.zip;*.xlsx", OverwritePrompt = true })
                {
                    if (dialog.ShowDialog(this) != DialogResult.OK || !Policy.Download(args.DownloadOperation.Uri, dialog.FileName, origin)) { args.Cancel = true; return; }
                    args.ResultFilePath = dialog.FileName;
                }
            };
            core.ProcessFailed += delegate { Failure("The desktop view needs to reopen. Choose Reload; the managed Stats session remains protected."); };
        }
        private void External(string url)
        {
            if (options.Preview || !Policy.External(url)) { status.Text = "This link cannot open from the desktop view."; return; }
            try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch (Exception) { status.Text = "Your default browser could not open the link."; }
        }
        private async Task Smoke()
        {
            try
            {
                var core = view.CoreWebView2;
                checks["syntheticPage"] = await core.ExecuteScriptAsync("document.querySelector('main').dataset.fixture === 'the-stats-preview'") == "true";
                checks["inPrivate"] = core.Profile.IsInPrivateModeEnabled;
                checks["hostObjectsDisabled"] = !core.Settings.AreHostObjectsAllowed;
                checks["webMessagesDisabled"] = !core.Settings.IsWebMessageEnabled;
                checks["devToolsDisabled"] = !core.Settings.AreDevToolsEnabled;
                checks["nativeIdentity"] = Text == "The Stats — [REDACTED]" && Icon != null;
                int originalWidth = Width;
                checks["headerDefaultWidth"] = HeaderFits(1440);
                checks["headerMinimumWidth"] = HeaderFits(MinimumSize.Width);
                Width = originalWidth;
                int before = blocked; core.Navigate("https://example.com/"); await Task.Delay(400);
                checks["externalNavigationBlocked"] = blocked > before && Policy.Local(core.Source, origin);
                var next = new TaskCompletionSource<bool>();
                EventHandler<CoreWebView2NavigationCompletedEventArgs> handler = delegate(object sender, CoreWebView2NavigationCompletedEventArgs args) { next.TrySetResult(args.IsSuccess); };
                core.NavigationCompleted += handler; core.Navigate(new Uri(origin, "next").AbsoluteUri);
                bool completed = await Task.WhenAny(next.Task, Task.Delay(8000)) == next.Task && await next.Task;
                core.NavigationCompleted -= handler;
                checks["localNavigation"] = completed && await core.ExecuteScriptAsync("document.body.textContent.includes('Local navigation verified')") == "true";
                bool success = true; foreach (var item in checks) success &= item.Value is bool && (bool)item.Value;
                FinishSmoke(success, null);
            }
            catch (Exception error) { FinishSmoke(false, error.GetType().Name + ": " + error.Message); }
        }
        private void FinishSmoke(bool success, string error)
        {
            if (disposed) return; ExitCode = success ? 0 : 3;
            Guard.Receipt(Path.Combine(options.Fixture, "smoke.json"), new { format = "the-stats-desktop-smoke-v1", syntheticOnly = true, success = success, checks = checks, error = error });
            BeginInvoke((Action)Close);
        }
    }

    internal static class SelfTests
    {
        private sealed class HealthStream : MemoryStream
        {
            private readonly bool stall;
            internal HealthStream(string value, bool stop) : base(Encoding.UTF8.GetBytes(value)) { stall = stop; }
            public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellation)
            {
                if (stall) return new TaskCompletionSource<int>().Task;
                return Task.FromResult(base.Read(buffer, offset, Math.Min(count, 1)));
            }
        }
        private sealed class HealthHandler : HttpMessageHandler
        {
            private readonly string value;
            private readonly bool stall;
            internal HealthHandler(string body, bool stop) { value = body; stall = stop; }
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellation)
            { return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(new HealthStream(value, stall)) }); }
        }
        internal static int Run(string fixture)
        {
            Guard.NewFixture(fixture); var checks = new Dictionary<string, bool>();
            Action<string, bool> check = delegate(string name, bool result) { checks[name] = result; };
            Action<string, Action> refusal = delegate(string name, Action action) { try { action(); checks[name] = false; } catch (Exception) { checks[name] = true; } };
            var origin = new Uri("http://127.0.0.1:8501/");
            check("sameOrigin", Policy.Local("http://127.0.0.1:8501/tiktok", origin));
            check("wrongPortRefused", !Policy.Local("http://127.0.0.1:8502/", origin));
            check("lookalikeHostRefused", !Policy.Local("http://127.0.0.1.evil:8501/", origin));
            check("credentialAuthorityRefused", !Policy.Local("http://user@127.0.0.1:8501/", origin));
            check("fileSchemeRefused", !Policy.Local("file:///C:/private.txt", origin));
            check("javascriptRefused", !Policy.External("javascript:alert(1)"));
            check("publicVideoLink", Policy.External("https://www.youtube.com/watch?v=synthetic"));
            check("secretLinkRefused", !Policy.External("https://example.com/?access_token=private"));
            check("encodedSecretLinkRefused", !Policy.External("https://example.com/?%74oken=private"));
            check("safeDocumentationAnchor", Policy.External("https://example.com/docs#source-definitions"));
            check("fragmentCredentialRefused", !Policy.External("https://example.com/#access_token=private"));
            check("authorizationCodeRefused", !Policy.External("https://example.com/?code=private"));
            check("encodedAuthorizationCodeRefused", !Policy.External("https://example.com/?%63ode=private"));
            check("externalResourceRefused", !Policy.Resource("https://example.com/script.js", origin));
            check("localWebsocket", Policy.Resource("ws://127.0.0.1:8501/_stcore/stream", origin));
            check("foreignWebsocketRefused", !Policy.Resource("ws://127.0.0.1:8502/_stcore/stream", origin));
            check("streamlitCsv", Policy.Download("http://127.0.0.1:8501/media/fixture.csv", "fixture.csv", origin));
            check("executableDownloadRefused", !Policy.Download("http://127.0.0.1:8501/media/fixture.exe", "fixture.exe", origin));
            check("externalDownloadRefused", !Policy.Download("https://example.com/media/fixture.csv", "fixture.csv", origin));
            string stoppedCopy = StatsWindow.FailureCopy("The Stats is not running.");
            check("stoppedCopyHasOneInstruction", Regex.Matches(stoppedCopy, "Reload").Count == 1 && Regex.Matches(stoppedCopy, "INTERLINKED").Count == 1 && stoppedCopy.Contains("Your existing library stays in its managed location."));
            refusal("productionAddressOverrideRefused", delegate { Options.Parse(new[] { "--url", "http://127.0.0.1:8501/" }); });
            refusal("existingFixtureRefused", delegate { Guard.NewFixture(fixture); });
            refusal("managedCacheFixtureRefused", delegate { Guard.NewFixture(Path.Combine(Guard.User, @"AppData\Local\ProjectLibrary\Cache\stats-active\fixture-refusal")); });
            refusal("historicalSnapshotFixtureRefused", delegate { Guard.NewFixture(Path.Combine(Path.GetDirectoryName(Guard.Source), @"windows-snapshots\fixture-refusal")); });
            string pin = Path.Combine(fixture, "pin.txt"); File.WriteAllText(pin, "fixture"); string digest = Guard.Digest(pin); Guard.Pin(pin, digest);
            File.WriteAllText(pin, "changed"); refusal("changedPinRefused", delegate { Guard.Pin(pin, digest); });
            string source = Path.Combine(fixture, "source"), python = Path.Combine(source, @".venv\Scripts\python.exe");
            var owner = new Dictionary<string, object> { { "format", "interlinked-stats-owner-v1" }, { "kit", Guard.Kit }, { "demo", false } };
            var config = new Dictionary<string, object> { { "format", "interlinked-stats-connection-v1" }, { "sourceRoot", source }, { "python", python }, { "port", 8501 }, { "launcherSha256", digest }, { "pythonSha256", digest }, { "lockSha256", digest } };
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var session = new Dictionary<string, object> { { "format", "interlinked-stats-session-v1" }, { "projectId", "stats-active" }, { "status", "RUNNING" }, { "pid", 123 }, { "utc", now.ToString("o") } };
            Func<int, ProcessIdentity> identity = delegate(int pid) { return new ProcessIdentity { Alive = true, Executable = python, Started = now.AddSeconds(-5) }; };
            check("matchingSession", Connection.Validate(owner, config, session, source, identity).Pid == 123);
            session["status"] = "IDLE"; refusal("idleSessionRefused", delegate { Connection.Validate(owner, config, session, source, identity); }); session["status"] = "RUNNING";
            refusal("wrongSourceRefused", delegate { Connection.Validate(owner, config, session, source + "-other", identity); });
            refusal("deadProcessRefused", delegate { Connection.Validate(owner, config, session, source, delegate(int pid) { return new ProcessIdentity { Alive = false, Executable = python, Started = now }; }); });
            refusal("reusedPidRefused", delegate { Connection.Validate(owner, config, session, source, delegate(int pid) { return new ProcessIdentity { Alive = true, Executable = python, Started = now.AddMinutes(1) }; }); });
            refusal("wrongExecutableRefused", delegate { Connection.Validate(owner, config, session, source, delegate(int pid) { return new ProcessIdentity { Alive = true, Executable = python + "-other", Started = now }; }); });
            using (var client = new HttpClient(new HealthHandler("ok", false)))
            { Connection.Healthy(client, origin, 1000).GetAwaiter().GetResult(); check("fragmentedHealthBody", true); }
            using (var client = new HttpClient(new HealthHandler("ok", true)))
            {
                bool timedOut = false; var clock = Stopwatch.StartNew();
                try { Connection.Healthy(client, origin, 50).GetAwaiter().GetResult(); } catch (TimeoutException) { timedOut = true; }
                check("stalledHealthBodyBounded", timedOut && clock.Elapsed < TimeSpan.FromSeconds(2));
            }
            using (var client = new HttpClient(new HealthHandler(new string('x', 100), false)))
            { refusal("oversizedHealthBodyRefused", delegate { Connection.Healthy(client, origin, 1000).GetAwaiter().GetResult(); }); }
            bool success = true; foreach (var result in checks) success &= result.Value;
            Guard.Receipt(Path.Combine(fixture, "self-test.json"), new { format = "the-stats-desktop-self-test-v1", syntheticOnly = true, success = success, checks = checks });
            return success ? 0 : 1;
        }
    }

    internal static class Program
    {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)] private static extern int SetCurrentProcessExplicitAppUserModelID(string value);
        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                var options = Options.Parse(args);
                if (options.SelfTest) return SelfTests.Run(options.Fixture);
                if (options.Preview) Guard.NewFixture(options.Fixture);
                SetCurrentProcessExplicitAppUserModelID("Redacted.TheStats.Desktop");
                string key = options.Preview ? Guard.Digest(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "TheStats.exe")).Substring(0, 12) + Guid.NewGuid().ToString("N") : "THIS-MACHINE-Jude";
                bool first;
                using (var mutex = new Mutex(true, @"Local\TheStats.Desktop." + key, out first))
                using (var activation = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\TheStats.Activate." + key))
                {
                    if (!first) { activation.Set(); return 0; }
                    var window = new StatsWindow(options);
                    ThreadPool.QueueUserWorkItem(delegate
                    {
                        while (!window.IsDisposed)
                        {
                            bool signaled;
                            try { signaled = activation.WaitOne(1000); } catch (ObjectDisposedException) { break; }
                            if (signaled && window.IsHandleCreated)
                                try { window.BeginInvoke((Action)window.ActivateWindow); } catch (InvalidOperationException) { }
                        }
                    });
                    Application.Run(window); mutex.ReleaseMutex(); return window.ExitCode;
                }
            }
            catch (Exception error)
            {
                if (args.Length > 0) return 2;
                MessageBox.Show(error.Message, "The Stats", MessageBoxButtons.OK, MessageBoxIcon.Warning); return 2;
            }
        }
    }
}
