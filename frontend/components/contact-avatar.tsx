"use client";

import { useState, type ReactNode } from "react";

/** The person's channel photo when Meta gave us one, otherwise their initial. A photo
 * that fails to load (expired CDN link) falls back to the initial too. */
export function ContactAvatar({
  name,
  avatarUrl,
  size = 36,
  className = "",
  children,
}: {
  name: string;
  avatarUrl?: string;
  size?: number;
  className?: string;
  children?: ReactNode;
}) {
  const [broken, setBroken] = useState(false);
  const letter = name?.trim().charAt(0).toUpperCase() || "?";
  const showImage = Boolean(avatarUrl) && !broken;
  return (
    <div
      className={`contact-avatar ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      data-photo={showImage ? "true" : undefined}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote Meta CDN photo
        <img
          src={avatarUrl}
          alt=""
          width={size}
          height={size}
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
        />
      ) : (
        <span aria-hidden="true">{letter}</span>
      )}
      {children}
    </div>
  );
}
