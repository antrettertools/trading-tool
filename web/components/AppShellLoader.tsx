"use client";

import dynamic from "next/dynamic";

// next/dynamic with ssr:false must be called from a Client Component.
const AppShell = dynamic(() => import("./AppShell"), { ssr: false });

export default function AppShellLoader() {
  return <AppShell />;
}
