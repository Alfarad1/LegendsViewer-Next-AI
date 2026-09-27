
using LegendsViewer.Backend.Extensions;
using LegendsViewer.Backend.Legends;
using LegendsViewer.Backend.Legends.Bookmarks;
using LegendsViewer.Backend.Legends.Interfaces;
using LegendsViewer.Backend.Legends.Maps;
using LegendsViewer.Backend.Logging;
using LegendsViewer.Frontend;
using Microsoft.AspNetCore.Connections;
using Microsoft.Extensions.Logging.Console;
using System.Text;
using System.Text.Json.Serialization;

namespace LegendsViewer.Backend;

public class Program
{
    private const string AllowAllOriginsPolicy = "AllowAllOrigins";
    public const uint BackendPort = 15421;
    public static readonly string BackendUrl = $"http://localhost:{BackendPort}";

    public static void Main(string[] args)
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

        var builder = WebApplication.CreateBuilder(args);
        builder.Services.AddCors(o => o.AddPolicy(AllowAllOriginsPolicy, builder =>
        {
            builder.AllowAnyOrigin()
                   .AllowAnyMethod()
                   .AllowAnyHeader();
        }));

        builder.WebHost.ConfigureKestrel(serverOptions =>
        {
            serverOptions.Limits.KeepAliveTimeout = TimeSpan.FromMinutes(5);
            serverOptions.Limits.RequestHeadersTimeout = TimeSpan.FromMinutes(5);
        })
        .UseUrls($"http://*:{BackendPort}");

        builder.Services.AddSingleton<IWorld, World>();
        builder.Services.AddSingleton<IWorldMapImageGenerator, WorldMapImageGenerator>();
        builder.Services.AddSingleton<IBookmarkService, BookmarkService>();
        builder.Services.AddClassicRepositories();

        builder.Services.AddControllers()
            .AddJsonOptions(options =>
            {
                // Serialize Enums as strings globally
                options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
            });

        builder.Services.AddEndpointsApiExplorer();
        builder.Services.AddSwaggerGen();

        builder.Logging.ClearProviders();
        builder.Logging.AddConsole(options => options.FormatterName = nameof(SimpleLogFormatter));
        builder.Logging.AddConsoleFormatter<SimpleLogFormatter, ConsoleFormatterOptions>();

        var app = builder.Build();

        if (app.Environment.IsDevelopment())
        {
            app.UseSwagger();
            app.UseSwaggerUI();
        }

        app.UseCors(AllowAllOriginsPolicy);

        app.UseAuthorization();
        app.MapControllers();

        var logger = app.Services.GetRequiredService<ILogger<Program>>();

        logger.LogInformation(AsciiArt.LegendsViewerLogo);
        logger.LogInformation("If the Legends Viewer frontend does not open automatically, you can access it directly by visiting:");
        logger.LogInformation(WebAppStaticServer.WebAppUrl);

        _ = WebAppStaticServer.RunAsync();

        var runningInContainer = string.Equals(
            Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER"),
            "true",
            StringComparison.OrdinalIgnoreCase);

        var openBrowser = Task.Delay(0);
        if (!app.Environment.IsDevelopment() && !runningInContainer)
        {
            openBrowser = WebAppStaticServer.OpenPageInBrowserAsync();
        }

        try
        {
            app.Run();
        }
        catch (IOException exception) when (exception.InnerException is AddressInUseException)
        {
            Console.WriteLine($"Address already in use: {BackendUrl}");
            Console.WriteLine("Skipping backend server.");
            Task.WaitAll(openBrowser);
        }
    }
}
