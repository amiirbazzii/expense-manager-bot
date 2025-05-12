// convex/queries.ts
import { v } from "convex/values";
import { query } from "./_generated/server";
import { Doc } from "./_generated/dataModel"; // Import Doc for typing expenses

// getExpenseSummary query (should be here from previous step)
export const getExpenseSummary = query({
  args: {
    telegramChatId: v.string(),
    startDate: v.number(),
    endDate: v.number(),
    category: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .filter((q) => q.eq(q.field("telegramChatId"), args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found.");
    }

    let expenseQuery = ctx.db
      .query("expenses")
      .withIndex("by_userId_date", (q) =>
        q.eq("userId", user._id)
         .gte("date", args.startDate)
         .lte("date", args.endDate)
      );
      // .order("desc"); // Already in the previous version, good for consistency

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
      category: args.category?.trim(),
      startDate: args.startDate,
      endDate: args.endDate,
    };
  },
});

// New query function for recent expenses
export const getRecentExpenses = query({
  args: {
    telegramChatId: v.string(),
    limit: v.optional(v.number()), // Optional limit for number of expenses
  },
  handler: async (ctx, args) => {
    // 1. Find the user
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .filter((q) => q.eq(q.field("telegramChatId"), args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found. Please /start or /register first.");
    }

    // 2. Determine the limit
    const limit = args.limit ?? 5; // Default to 5 if no limit is provided
    if (limit <= 0 || limit > 50) { // Add some reasonable bounds for the limit
        throw new Error("Limit must be between 1 and 50.");
    }

    // 3. Query expenses, order by date descending (most recent first), and apply limit
    const recentExpenses: Doc<"expenses">[] = await ctx.db
      .query("expenses")
      .withIndex("by_userId_date", (q) => q.eq("userId", user._id)) // Filter by user
      .order("desc") // Order by the 'date' field implicitly (most recent first due to how by_userId_date index is likely structured or by default _creationTime if date isn't the first sort field in index)
                     // To be explicit for 'date' field from schema: .order("desc", "date") if 'date' is an indexed field suitable for primary sort.
                     // Convex orders by index fields. If "by_userId_date" is ["userId", "date"], then .order("desc") on this query will sort by date descending for that user.
      .take(limit); // Take the top 'limit' expenses

    // 4. Return the expenses (or a subset of fields if needed)
    // We are returning full documents, which is fine for this case.
    return recentExpenses.map(expense => ({
        // Optionally, transform the data here if needed, e.g., formatting date
        // For now, return essential fields.
        _id: expense._id,
        amount: expense.amount,
        category: expense.category,
        description: expense.description,
        date: expense.date, // This is a timestamp
    }));
  },
});
