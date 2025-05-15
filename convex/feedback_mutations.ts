// convex/feedback_mutations.ts
import { v } from "convex/values";
import { mutation } from "./_generated/server";
import { Id } from "./_generated/dataModel";

export const recordCategoryFeedback = mutation({
  args: {
    telegramChatId: v.string(), // To find the user's Convex ID
    original_text_for_ai: v.string(),
    ai_predicted_category: v.optional(v.string()),
    ai_confidence: v.optional(v.float64()),
    user_chosen_category: v.string(),
    // expenseId: v.optional(v.id("expenses")) // Optional: if you want to link to the specific expense
  },
  handler: async (ctx, args) => {
    // 1. Find the user
    const user = await ctx.db
      .query("users")
      .withIndex("by_telegram_chat_id", (q) => q.eq("telegramChatId", args.telegramChatId))
      .unique();

    if (!user) {
      // If user not found, we probably shouldn't record feedback,
      // or record it without a userId if that's acceptable (less useful).
      console.warn(`User not found for telegramChatId: ${args.telegramChatId}. Feedback not recorded.`);
      // Optionally throw an error, or return a specific status
      // throw new Error("User not found, cannot record feedback.");
      return { success: false, message: "User not found for feedback." };
    }

    // 2. Determine if it was a correction
    let is_correction = false;
    if (args.ai_predicted_category !== null && args.ai_predicted_category !== undefined) { // AI made a prediction
        if (args.ai_predicted_category.trim().toLowerCase() !== args.user_chosen_category.trim().toLowerCase()) {
            is_correction = true;
        }
    } else { 
        // If AI made no prediction, any user choice is essentially new info, not a "correction" of AI.
        // Or you could define it as a correction if AI failed and user provided something.
        // For now, let's say it's a correction if AI predicted something and it was different.
        // If AI didn't predict, it's just user input.
        // We can refine this logic based on how you want to use the `is_correction` flag.
        // If ai_predicted_category is null/undefined, perhaps `is_correction` should be false or a different flag used.
        // For simplicity now: if AI predicted and it's different, it's a correction.
    }


    // 3. Insert the feedback
    const feedbackId: Id<"category_feedback"> = await ctx.db.insert("category_feedback", {
      userId: user._id,
      original_text_for_ai: args.original_text_for_ai,
      ai_predicted_category: args.ai_predicted_category,
      ai_confidence: args.ai_confidence,
      user_chosen_category: args.user_chosen_category,
      is_correction: is_correction,
      timestamp: Date.now(), // Current server timestamp
      // expenseId: args.expenseId // If you pass it
    });

    console.log(`Category feedback recorded: ${feedbackId} for user ${user._id}`);
    return { success: true, feedbackId: feedbackId };
  },
});
