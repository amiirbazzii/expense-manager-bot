// convex/expenses.ts
import { v } from "convex/values";
import { mutation, internalQuery } from "./_generated/server"; // Ensure this line is present
import { Doc, Id } from "./_generated/dataModel"; // Ensure this line is present

// ... (getUserByTelegramChatId if you have it) ...

export const logExpense = mutation({ // <--- MUST be 'export const logExpense'
  args: {
    telegramChatId: v.string(),
    amount: v.number(),
    category: v.string(),
    description: v.optional(v.union(v.string(), v.null())), // Allow null values
    date: v.number(),
  },
  handler: async (ctx, args) => {
    // ... your logic ...
    const user = await ctx.db
      .query("users")
      .filter((q) => q.eq(q.field("telegramChatId"), args.telegramChatId))
      .unique();

    if (!user) {
      throw new Error("User not found. Please register or log in first.");
    }
    // ... rest of the validation and insert logic ...
    const expenseId: Id<"expenses"> = await ctx.db.insert("expenses", {
      userId: user._id,
      amount: args.amount,
      category: args.category.trim(),
      description: args.description?.trim() || undefined, // Handle null or undefined description
      date: args.date,
    });

    return { success: true, expenseId: expenseId };
  },
});