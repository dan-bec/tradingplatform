using Microsoft.EntityFrameworkCore;

namespace BullseyeDesktop.Shared.Data
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
