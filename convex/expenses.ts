// convex/expenses.ts
import { v } from "convex/values";
import { mutation } from "./_generated/server"; // Note: 'query' import removed if no queries left
import { Id } from "./_generated/dataModel";

// logExpense mutation (should be here from previous step)
export const logExpense = mutation({
  args: {
    telegramChatId: v.string(),
    amount: v.number(),
    category: v.string(),
    description: v.optional(v.union(v.string(), v.null())),
    date: v.number(), // Timestamp (milliseconds since epoch)
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .filter((q) => q.eq(q.field("telegramChatId"), args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found. Please /start or /register first.");
    }
    if (args.amount <= 0) {
        throw new Error("Expense amount must be positive.");
    }
    if (!args.category || args.category.trim() === "") {
        throw new Error("Category cannot be empty.");
    }
    if (args.date > Date.now() + (24*60*60*1000)) {
        throw new Error("Expense date cannot be in the distant future.");
    }
     if (args.date < 0) {
        throw new Error("Invalid expense date provided.");
    }

    const expenseId: Id<"expenses"> = await ctx.db.insert("expenses", {
      userId: user._id,
      amount: args.amount,
      category: args.category.trim(),
      description: args.description?.trim() || undefined,
      date: args.date,
    });
    return { success: true, expenseId: expenseId, message: "Expense logged!" };
  },
});

// getExpenseSummary has been moved to convex/queries.ts
