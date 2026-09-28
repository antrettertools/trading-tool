import AppShellLoader from "@/components/AppShellLoader";

// The whole app is an interactive, localStorage-backed dashboard (charts,
// live polling, paper trading) with nothing worth server-rendering, so it's
// loaded client-only — this also sidesteps any SSR/localStorage hydration
// mismatch concerns entirely.
export default function Page() {
  return <AppShellLoader />;
}
