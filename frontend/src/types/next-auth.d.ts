import { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      hasCanvas: boolean;
    } & DefaultSession["user"];
    accessToken: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    userId?: string;
    hasCanvas?: boolean;
    accessToken?: string;
    refreshToken?: string;
    googleId?: string;
  }
}
