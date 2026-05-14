export function CatPoseReady() {
  return (
    <svg viewBox="0 0 320 220" className="w-full max-w-[360px]">
      {/* grass */}
      <g fill="#2f6b1f">
        {Array.from({ length: 42 }).map((_, i) => (
          <circle key={i} cx={20 + i * 7} cy={190} r="2.2" />
        ))}
      </g>

      {/* cat body */}
      <g fill="none" stroke="#161616" strokeWidth="5" strokeLinecap="round" strokeDasharray="0.1 12">
        {/* body */}
        <path d="M92 125 C115 72, 205 78, 235 122" />

        {/* head */}
        <path d="M220 105 C250 88, 282 105, 285 138 C287 168, 255 182, 228 165" />

        {/* ears */}
        <path d="M232 102 L238 70 L258 99" />
        <path d="M262 101 L282 75 L282 112" />

        {/* tail */}
        <path d="M90 126 C55 112, 55 70, 82 50" />
        <path d="M82 50 C64 28, 70 12, 90 20" />

        {/* front legs crouched */}
        <path d="M220 155 C235 168, 250 174, 270 170" />
        <path d="M210 150 C225 165, 232 178, 230 190" />

        {/* back legs crouched */}
        <path d="M105 140 C80 150, 70 168, 82 184" />
        <path d="M125 145 C110 165, 110 180, 128 188" />

        {/* face */}
        <path d="M246 132 L286 128" />
        <path d="M246 142 L286 148" />
        <path d="M246 152 L280 168" />
        <path d="M252 150 C258 158, 268 158, 274 150" />
      </g>

      {/* eyes / nose */}
      <g fill="#161616">
        <circle cx="248" cy="124" r="4" />
        <circle cx="270" cy="126" r="4" />
        <circle cx="263" cy="142" r="3" />
      </g>
    </svg>
  );
}