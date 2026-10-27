"use client";

import { useSyncExternalStore } from "react";

const DEMO_USERS = ["demo-agent", "demo-team-lead", "demo-compliance"] as const;
const DEFAULT_USER = DEMO_USERS[0];

function setDemoUserCookie(user: string) {
  document.cookie = `demo_user=${user}; path=/`;
}

function readDemoUserCookie(): string {
  const match = document.cookie.match(/(?:^|;\s*)demo_user=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : DEFAULT_USER;
}

// The cookie only changes via select(), which reloads the page, so there is
// nothing to subscribe to. useSyncExternalStore (not a lazy useState) keeps
// the server render on DEFAULT_USER and swaps in the cookie value on hydration
// without a mismatch warning.
const noSubscribe = () => () => {};

export function DemoUserSwitcher() {
  const current = useSyncExternalStore(noSubscribe, readDemoUserCookie, () => DEFAULT_USER);

  function select(user: string) {
    setDemoUserCookie(user);
    window.location.reload(); // simplest correctness: re-fetch every server component with the new identity
  }

  return (
    <div className="flex gap-2 items-center p-2 border-b bg-neutral-50">
      <span className="text-sm text-neutral-500">Acting as:</span>
      {DEMO_USERS.map((user) => (
        <button key={user} onClick={() => select(user)} className={`text-sm px-2 py-1 rounded ${user === current ? "bg-black text-white" : "bg-white border"}`}>
          {user}
        </button>
      ))}
    </div>
  );
}
