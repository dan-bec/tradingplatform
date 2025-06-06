using Microsoft.EntityFrameworkCore;

namespace Bullseye.Shared.Data
{
    // The main context class for the apps DB operations
    public class ApplicationDbContext : DbContext
    {
        public ApplicationDbContext(DbContextOptions<ApplicationDbContext> options)
        : base(options)
        {
        }
    }
}
