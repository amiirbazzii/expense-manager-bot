// convex/queries.ts
import { v } from "convex/values";
import { query } from "./_generated/server";
// Id might not be strictly needed here if not constructing IDs, but good for consistency
import { Id } from "./_generated/dataModel"; 

export const getExpenseSummary = query({
  args: {
    telegramChatId: v.string(),
    startDate: v.number(), // Start timestamp (milliseconds)
    endDate: v.number(),   // End timestamp (milliseconds)
    category: v.optional(v.string()), // Optional category to filter by
  },
  handler: async (ctx, args) => {
    // 1. Find the user
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .filter((q) => q.eq(q.field("telegramChatId"), args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found.");
    }

    // 2. Build the query for expenses
    // Using the by_userId_date index for efficient filtering on user and date range.
    let expenseQuery = ctx.db
      .query("expenses")
      .withIndex("by_userId_date", (q) =>
        q.eq("userId", user._id)
         .gte("date", args.startDate)
         .lte("date", args.endDate)
      );
      // Order by date, most recent first (optional, but good for some UIs)
      // .order("desc"); // Uncomment if you want to order by date descending

    // 3. Collect expenses and then filter by category if provided
    // This approach (collect then filter for category) is simpler for now.
    // For very large datasets, more advanced category filtering at the DB level might be needed.
    const expensesInRange = await expenseQuery.collect();
    
    let filteredExpenses = expensesInRange;
    if (args.category && args.category.trim() !== "") {
      const categoryToFilter = args.category.trim().toLowerCase();
      filteredExpenses = expensesInRange.filter(
        (expense) => expense.category.toLowerCase() === categoryToFilter
      );
    }
      
    let totalAmount = 0;
    for (const expense of filteredExpenses) {
      totalAmount += expense.amount;
    }

    return {
      count: filteredExpenses.length,
      totalAmount: totalAmount,
      category: args.category?.trim(), // Return the category used for filtering, if any
      startDate: args.startDate,
      endDate: args.endDate,
    };
  },
});
