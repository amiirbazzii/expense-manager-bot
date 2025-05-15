// convex/schema.ts
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // Users table (existing)
  users: defineTable({
    username: v.string(), 
    hashedPassword: v.string(), 
    telegramChatId: v.optional(v.string()), 
  })
  .index("by_username", ["username"])
  .index("by_telegram_chat_id", ["telegramChatId"]),

  // Expenses table (existing)
  expenses: defineTable({
    userId: v.id("users"),
    amount: v.number(),
    category: v.string(),
    description: v.optional(v.string()),
    date: v.number(), // Timestamp (milliseconds since epoch)
  })
  .index("by_userId_date", ["userId", "date"])
  .index("by_userId_category", ["userId", "category"]),

  // New table for category feedback
  category_feedback: defineTable({
    userId: v.id("users"),                      // Link to the user who provided the feedback
    original_text_for_ai: v.string(),         // The text snippet sent to the AI for categorization
    ai_predicted_category: v.optional(v.string()), // Category predicted by the AI
    ai_confidence: v.optional(v.float64()),     // Confidence score from the AI
    user_chosen_category: v.string(),         // The category ultimately confirmed or chosen by the user
    is_correction: v.boolean(),               // True if user_chosen_category differs from ai_predicted_category (and AI made a prediction)
    timestamp: v.number(),                    // When this feedback was recorded (e.g., Date.now())
    // Optional: store expenseId if you want to link feedback directly to a logged expense
    // expenseId: v.optional(v.id("expenses")) 
  }).index("by_userId", ["userId"]) // Index to query feedback by user
   .index("by_ai_predicted_category", ["ai_predicted_category"]) // Index for analysis
   .index("by_user_chosen_category", ["user_chosen_category"]), // Index for analysis
});
