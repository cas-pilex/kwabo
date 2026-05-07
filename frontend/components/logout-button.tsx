"use client";

import { authLogout } from "@/lib/api";

export function LogoutButton() {
  async function handleLogout() {
    await authLogout();
    window.location.href = "/login";
  }
  return (
    <button
      onClick={handleLogout}
      className="text-sm font-medium text-white/80 hover:text-white"
      title="Uitloggen"
    >
      Logout
    </button>
  );
}
