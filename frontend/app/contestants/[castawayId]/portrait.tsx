"use client";

import { useState } from "react";

export default function Portrait({
  name,
  src
}: {
  name: string;
  src?: string;
}) {
  const [failed, setFailed] = useState(false);
  const initials = name
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
  if (!src || failed) {
    return (
      <div
        className="portraitFallback"
        role="img"
        aria-label={`Portrait unavailable for ${name}`}
      >
        <strong aria-hidden="true">{initials}</strong>
        <span>Photo unavailable</span>
      </div>
    );
  }
  // The photo is served directly by its official publisher; retain its source credit below.
  return (
    <img
      className="contestantPortrait"
      src={src}
      alt={`Official cast portrait of ${name}`}
      width={1024}
      height={683}
      onError={() => setFailed(true)}
    />
  );
}
