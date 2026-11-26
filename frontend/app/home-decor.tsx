export default function HomeDecor() {
  return (
    <svg className="hero-deco" viewBox="0 0 600 220" aria-hidden="true" focusable="false">
      <path className="spark s1" d="M60 70l5 15 15 5-15 5-5 15-5-15-15-5 15-5z" />
      <path className="spark s2" d="M548 52l4 11 11 4-11 4-4 11-4-11-11-4 11-4z" />
      <path className="spark s3" d="M520 168l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" />
      <path className="spark s4" d="M92 176l3 7 7 3-7 3-3 7-3-7-7-3 7-3z" />
      <g className="bloom b1" transform="translate(30 132)">
        <circle r="6" cx="0" cy="-8" /><circle r="6" cx="7.6" cy="-2.5" />
        <circle r="6" cx="4.7" cy="6.5" /><circle r="6" cx="-4.7" cy="6.5" />
        <circle r="6" cx="-7.6" cy="-2.5" /><circle className="core" r="3" />
      </g>
      <g className="bloom b2" transform="translate(575 120) scale(.75)">
        <circle r="6" cx="0" cy="-8" /><circle r="6" cx="7.6" cy="-2.5" />
        <circle r="6" cx="4.7" cy="6.5" /><circle r="6" cx="-4.7" cy="6.5" />
        <circle r="6" cx="-7.6" cy="-2.5" /><circle className="core" r="3" />
      </g>
    </svg>
  );
}
