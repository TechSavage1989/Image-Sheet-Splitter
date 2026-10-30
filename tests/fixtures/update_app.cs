// Disposable native executables for the real PowerShell replacement tests.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Reflection;
[assembly: AssemblyProduct("Image Sheet Splitter")]
#if PRIOR
[assembly: AssemblyFileVersion("1.6.0")]
#else
[assembly: AssemblyFileVersion("1.7.0")]
#endif
class UpdateFixture {
    static void Main(string[] args) {
        var json = new JavaScriptSerializer();
#if PRIOR
        File.WriteAllText(Environment.GetEnvironmentVariable("ISS_TEST_ROLLBACK"), json.Serialize(args));
#else
        var options = new Dictionary<string, string>();
        for (int i = 0; i + 1 < args.Length; i += 2) options[args[i]] = args[i + 1];
        File.WriteAllText(Environment.GetEnvironmentVariable("ISS_TEST_ARGS"), json.Serialize(options));
        string mode = Environment.GetEnvironmentVariable("ISS_TEST_MODE");
        if (mode == "exit") return;
        if (mode == "timeout") { Thread.Sleep(60000); return; }
        var health = new Dictionary<string, object> {
            {"status", "healthy"},
            {"version", mode == "version" ? "1.6.0" : "1.7.0"},
            {"token", mode == "token" ? "stale-token" : options["--post-update-token"]},
            {"pid", mode == "pid" ? 4 : Process.GetCurrentProcess().Id},
            {"executable", Process.GetCurrentProcess().MainModule.FileName}
        };
        string marker = options["--post-update-health"];
        File.WriteAllText(marker + ".tmp", mode == "malformed" ? "not json" : json.Serialize(health));
        File.Move(marker + ".tmp", marker);
        Thread.Sleep(60000);
#endif
    }
}
