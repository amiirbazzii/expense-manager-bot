    // convex/schema.ts
    import { defineSchema, defineTable } from "convex/server";
    import { v } from "convex/values";

    export default defineSchema({
      // Users table to store user information
      users: defineTable({
        username: v.string(), // User's chosen username
        hashedPassword: v.string(), // User's securely hashed password
        telegramChatId: v.optional(v.string()), // User's Telegram chat ID for easy linking
      })
      .index("by_username", ["username"]) // Index for quick lookup by username
      .index("by_telegram_chat_id", ["telegramChatId"]), // Index for quick lookup by Telegram Chat ID

      // Expenses table to store expense records
      expenses: defineTable({
        userId: v.id("users"),
        amount: v.number(),
        category: v.string(),
        description: v.optional(v.string()),
        date: v.number(), // Timestamp (milliseconds since epoch)
      })
      .index("by_userId_date", ["userId", "date"])
      .index("by_userId_category", ["userId", "category"]),
    });
    