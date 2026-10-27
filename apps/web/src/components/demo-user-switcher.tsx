"use client";

import { useState } from "react";

const DEMO_USERS = ["demo-agent", "demo-team-lead", "demo-compliance"] as const;

function setDemoUserCookie(user: string) {
  document.cookie = `demo_user=${user}; path=/`;
}

export function DemoUserSwitcher() {
  const [current, setCurrent] = useState<string>(DEMO_USERS[0]);

  function select(user: string) {
    setDemoUserCookie(user);
    setCurrent(user);
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
