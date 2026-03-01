import { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          scope: [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/calendar",
          ].join(" "),
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      // On initial sign in, save tokens and sync with backend
      if (account && profile) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.googleId = account.providerAccountId;

        // Sync user with backend
        try {
          const response = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/auth/google`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                google_id: account.providerAccountId,
                email: profile.email,
                name: profile.name,
                access_token: account.access_token,
                refresh_token: account.refresh_token,
              }),
            }
          );

          if (response.ok) {
            const user = await response.json();
            token.userId = user.id;
            token.hasCanvas = user.has_canvas;
          }
        } catch (error) {
          console.error("Failed to sync with backend:", error);
        }
      }

      return token;
    },
    async session({ session, token }) {
      // Expose custom fields to the client session
      session.user.id = token.userId as string;
      session.user.hasCanvas = token.hasCanvas as boolean;
      session.accessToken = token.accessToken as string;

      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
};
