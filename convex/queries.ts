// convex/queries.ts
import { v } from "convex/values";
import { query } from "./_generated/server";
import { Doc } from "./_generated/dataModel";

// getExpenseSummary query (from previous steps)
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

// getRecentExpenses query (from previous steps)
export const getRecentExpenses = query({
  args: {
    telegramChatId: v.string(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found. Please /start or /register first.");
    }

    const limit = args.limit ?? 5;
    if (limit <= 0 || limit > 50) {
        throw new Error("Limit must be between 1 and 50.");
    }

    const recentExpenses: Doc<"expenses">[] = await ctx.db
      .query("expenses")
      .withIndex("by_userId_date", (q) => q.eq("userId", user._id))
      .order("desc")
      .take(limit);

    return recentExpenses.map(expense => ({
        _id: expense._id.toString(), // Ensure ID is string for CSV if needed
        amount: expense.amount,
        category: expense.category,
        description: expense.description,
        date: expense.date,
    }));
  },
});

// New query function for fetching all expenses for a report
export const getExpensesForReport = query({
  args: {
    telegramChatId: v.string(),
    startDate: v.number(), // Start timestamp (milliseconds)
    endDate: v.number(),   // End timestamp (milliseconds)
    // Optional: category could be added here too if needed for CSV reports
    // category: v.optional(v.string()), 
  },
  handler: async (ctx, args) => {
    // 1. Find the user
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found. Please /start or /register first.");
    }

    // 2. Query expenses within the date range for the user
    // Using the by_userId_date index for efficient filtering.
    // Order by date ascending for the report.
    const expensesToReport: Doc<"expenses">[] = await ctx.db
      .query("expenses")
      .withIndex("by_userId_date", (q) => 
        q.eq("userId", user._id)
         .gte("date", args.startDate)
         .lte("date", args.endDate)
      )
      .order("asc") // Order by date ascending for chronological report
      .collect();

    // 3. Return the expenses, potentially transforming fields for CSV friendliness
    return expensesToReport.map(expense => ({
        // Convert Convex Id to string if it's not already for easier CSV handling
        // _id: expense._id.toString(), 
        date: expense.date, // Keep as timestamp, will be formatted in Python
        category: expense.category,
        amount: expense.amount,
        description: expense.description ?? "", // Ensure description is a string, not null
    }));
  },
});
