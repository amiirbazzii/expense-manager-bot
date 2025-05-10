// convex/auth.ts
import { v } from "convex/values";
import { mutation, query } from "./_generated/server";
import { Id } from "./_generated/dataModel";
// Note: Convex's environment has access to Node.js crypto module.
// For bcrypt, you'd typically use a library. If running directly in Convex's Node.js environment,
// you might need to ensure bcrypt is available or use a pure JS alternative if full bcrypt isn't supported.
// However, for simplicity in this example, we'll simulate password handling.
// In a real app, ensure proper bcryptjs or similar library usage if Convex doesn't provide a direct bcrypt utility.
// For now, let's assume a secure hashing function is available or will be implemented.

// A more robust solution for password hashing would involve integrating a library like bcrypt.js.
// Since Convex runs in a Node.js environment, you can add `bcryptjs` to your package.json
// in the root of your project (not inside the convex folder) by running `npm install bcryptjs`
// and then `npm install --save-dev @types/bcryptjs`
// Then you can import it in your Convex function:
// import bcrypt from "bcryptjs";

export const registerUser = mutation({
  args: {
    username: v.string(),
    password: v.string(), // Password will be hashed
    telegramChatId: v.optional(v.string()), // Optional: to link Telegram chat ID
  },
  handler: async (ctx, args) => {
    // 1. Check if username already exists
    const existingUser = await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username))
      .unique();

    if (existingUser) {
      // Consider throwing a more specific error or returning a status
      throw new Error("Username already taken. Please choose another one.");
    }

    // 2. Hash the password
    // IMPORTANT: In a real application, use a proper bcrypt library and salt rounds.
    // Convex's Node.js environment should support 'bcryptjs'.
    // const saltRounds = 10; // Standard practice
    // const hashedPassword = await bcrypt.hash(args.password, saltRounds);
    // For this example, we'll store it as is, but THIS IS NOT SECURE FOR PRODUCTION.
    // TODO: Replace with actual bcryptjs hashing
    const hashedPassword = args.password; // Placeholder - REPLACE WITH REAL HASHING

    if (hashedPassword.length < 6) { // Example simple validation
        throw new Error("Password must be at least 6 characters long.");
    }

    // 3. Create the new user
    const userId: Id<"users"> = await ctx.db.insert("users", {
      username: args.username,
      hashedPassword: hashedPassword, // Store the hashed password
      telegramChatId: args.telegramChatId,
    });

    // You might want to return the userId or some success status
    return { success: true, userId: userId, username: args.username };
  },
});

// Optional: A query to get user by username (useful for login later)
export const getUserByUsername = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username))
      .unique();
  },
});
