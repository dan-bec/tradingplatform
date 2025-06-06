using BlazorDesktop.Hosting;
using BullseyeDesktop.Components;
using BullseyeDesktop.Shared.Data;
using BullseyeDesktop.Shared.Tasks;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.EntityFrameworkCore;

var builder = BlazorDesktopHostBuilder.CreateDefault(args);

builder.RootComponents.Add<Routes>("#app");
builder.RootComponents.Add<HeadOutlet>("head::after");

if (builder.HostEnvironment.IsDevelopment())
{
    builder.UseDeveloperTools();
}

// EF Core
var connectionString =
    builder.Configuration.GetConnectionString("DefaultConnection")
        ?? throw new InvalidOperationException("Connection string"
        + "'DefaultConnection' not found.");

builder.Services.AddDbContext<ApplicationDbContext>(options =>
    options.UseSqlite(connectionString));

builder.Services.AddSingleton<BackgroundTask>();

await builder.Build().RunAsync();
