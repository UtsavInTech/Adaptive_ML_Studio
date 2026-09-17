/** The AdaptiveML Studio mark.
 *
 * A minimal geometric reading of what the platform actually shows: a stream of data points running
 * left to right, a dashed baseline that keeps going flat after the concept changes, and a solid
 * curve that dips and then climbs back — a model adapting. No brains, no robots.
 */

export default function Logo({ size = 28, title = "AdaptiveML Studio" }: { size?: number; title?: string }) {
  return (
    <svg
      className="brand-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label={title}
    >
      {/* the static baseline: unchanged by the drift, and left behind by it */}
      <path
        d="M3 19 H29"
        stroke="currentColor"
        strokeOpacity="0.3"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="3 3.5"
      />
      {/* the adaptive curve: steady, a dip at the change, then recovery */}
      <path
        className="adaptive-path"
        d="M3 13 H11 C13.5 13 13.8 24 16.5 24 C19.5 24 19.5 9 23 9 H29"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* data points along the stream */}
      <circle cx="3" cy="13" r="2.1" fill="currentColor" />
      <circle cx="16.5" cy="24" r="2.1" fill="currentColor" fillOpacity="0.55" />
      <circle cx="29" cy="9" r="2.6" fill="currentColor" />
    </svg>
  );
}
