import { NextResponse } from "next/server";

import { auth } from "@/infrastructure/auth/auth";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/roadmap",
  "/courses",
  "/lessons",
  "/exercises",
  "/quizzes",
  "/projects",
  "/career",
  "/profile",
  "/playground",
];
const AUTH_ONLY_PATHS = ["/login", "/register"];

export const proxy = auth((request) => {
  const { pathname } = request.nextUrl;
  const isAuthenticated = !!request.auth?.user;

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (isProtected && !isAuthenticated) {
    const loginUrl = new URL("/login", request.nextUrl.origin);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (AUTH_ONLY_PATHS.includes(pathname) && isAuthenticated) {
    return NextResponse.redirect(new URL("/dashboard", request.nextUrl.origin));
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
