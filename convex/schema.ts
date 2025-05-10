// convex/schema.ts
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // Users table to store user information
  users: defineTable({
    username: v.string(), // User's chosen username
    hashedPassword: v.string(), // User's securely hashed password
    telegramChatId: v.optional(v.string()), // User's Telegram chat ID for easy linking (optional for now)
    // _creationTime is automatically added by Convex
  }).index("by_username", ["username"]), // Index for quick lookup by username

  // Expenses table to store expense records
  expenses: defineTable({
    userId: v.id("users"), // Link to the users table (ID of the user who logged the expense)
    amount: v.number(), // The amount of the expense
    category: v.string(), // The category of the expense (free text for Phase 1)
    description: v.optional(v.string()), // Optional description of the expense
    date: v.number(), // Date of the expense (stored as a timestamp, e.g., milliseconds since epoch)
    // _creationTime is automatically added by Convex (when the expense was logged)
  })
  .index("by_userId_date", ["userId", "date"]) // Index for querying expenses by user and sorting/filtering by date
  .index("by_userId_category", ["userId", "category"]), // Index for querying expenses by user and category
});
