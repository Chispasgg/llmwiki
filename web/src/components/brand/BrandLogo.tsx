"use client";

interface BrandLogoProps {
  logo?: string | null;
  size?: number;
  className?: string;
  rounded?: boolean;
}

/**
 * Pure presentational component: receives `logo` as a prop, never fetches.
 * If `logo` is a data-URI it renders an <img> (no inline SVG for security).
 * Otherwise renders the default chevron-in-rounded-rect icon.
 */
export function BrandLogo({
  logo,
  size = 32,
  className,
  rounded = false,
}: BrandLogoProps) {
  if (logo) {
    return (
      <img
        src={logo}
        alt="Logo"
        width={size}
        height={size}
        className={[
          "object-contain",
          rounded ? "rounded" : "",
          className ?? "",
        ]
          .filter(Boolean)
          .join(" ")}
      />
    );
  }

  // Default: chevron-in-rounded-rect matching icon.svg
  // rect fill=currentColor, polyline in background color (inverted for readability)
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      className={className}
    >
      <rect width="32" height="32" rx="7" fill="currentColor" />
      <polyline
        points="11,8 21,16 11,24"
        fill="none"
        stroke="hsl(var(--background))"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
