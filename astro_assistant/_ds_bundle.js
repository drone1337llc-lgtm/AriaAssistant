/* @ds-bundle: {"format":3,"namespace":"AstroBudDesignSystem_8da794","components":[{"name":"AriaAvatar","sourcePath":"components/companion/AriaAvatar.jsx"},{"name":"Kbd","sourcePath":"components/companion/Kbd.jsx"},{"name":"MoodMeter","sourcePath":"components/companion/MoodMeter.jsx"},{"name":"SpeechBubble","sourcePath":"components/companion/SpeechBubble.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Metric","sourcePath":"components/core/Metric.jsx"},{"name":"PaperPanel","sourcePath":"components/core/PaperPanel.jsx"},{"name":"Select","sourcePath":"components/core/Select.jsx"},{"name":"Slider","sourcePath":"components/core/Slider.jsx"},{"name":"StatusPill","sourcePath":"components/core/StatusPill.jsx"},{"name":"Toggle","sourcePath":"components/core/Toggle.jsx"}],"sourceHashes":{"components/companion/AriaAvatar.jsx":"f27cd5f13b63","components/companion/Kbd.jsx":"d48ae20f35ed","components/companion/MoodMeter.jsx":"66f03d7929ba","components/companion/SpeechBubble.jsx":"eed29f6a11b4","components/core/Badge.jsx":"518e59c2e446","components/core/Button.jsx":"50ade971488b","components/core/Metric.jsx":"b164294651a8","components/core/PaperPanel.jsx":"1524247bf9c2","components/core/Select.jsx":"9d9e704cdf44","components/core/Slider.jsx":"f3ddab5ebc91","components/core/StatusPill.jsx":"11dc6f36c106","components/core/Toggle.jsx":"9a7f76b97ec5","ui_kits/chat_window/chat.jsx":"e64b8e7ad8ac","ui_kits/chat_window/tweaks-panel.jsx":"6591467622ed","ui_kits/control_matrix/dashboard.jsx":"20525ef2f214","ui_kits/control_matrix/panels.jsx":"4d982b167a17"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.AstroBudDesignSystem_8da794 = window.AstroBudDesignSystem_8da794 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/companion/AriaAvatar.jsx
try { (() => {
const AURA = {
  1: 'var(--aura-1)',
  2: 'var(--aura-2)',
  3: 'var(--aura-3)',
  4: 'var(--aura-4)',
  5: 'var(--aura-5)'
};
const RING = {
  1: 'var(--mood-1)',
  2: 'var(--mood-2)',
  3: 'var(--mood-3)',
  4: 'var(--mood-4)',
  5: 'var(--mood-5)'
};

/**
 * Aria herself — a round portrait wrapped in a soft mood aura whose hue & spread
 * track her 1–5 mood. The brand's living centerpiece. Pass a real render via src.
 */
function AriaAvatar({
  src = 'assets/aria-avatar-round.png',
  mood = 3,
  size = 96,
  ring = true,
  float = false,
  alt = 'Aria',
  style = {}
}) {
  const m = Math.max(1, Math.min(5, Math.round(mood)));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: size,
      height: size,
      borderRadius: '50%',
      position: 'relative',
      boxShadow: AURA[m],
      transition: 'box-shadow .5s ease',
      animation: float ? 'aria-float 4.2s ease-in-out infinite' : 'none',
      ...style
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: alt,
    width: size,
    height: size,
    style: {
      width: '100%',
      height: '100%',
      borderRadius: '50%',
      objectFit: 'cover',
      display: 'block',
      border: ring ? '2.5px solid ' + RING[m] : 'none',
      boxSizing: 'border-box',
      background: 'var(--washi-100)'
    }
  }), /*#__PURE__*/React.createElement("style", null, '@keyframes aria-float{0%,100%{transform:translateY(-4px)}50%{transform:translateY(4px)}}'));
}
Object.assign(__ds_scope, { AriaAvatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/companion/AriaAvatar.jsx", error: String((e && e.message) || e) }); }

// components/companion/Kbd.jsx
try { (() => {
/** Keyboard chip — renders Aria's global hotkeys (Ctrl+Shift+Space) as keycaps. */
function Kbd({
  keys = [],
  children,
  style = {}
}) {
  const parts = keys.length ? keys : String(children || '').split('+').map(k => k.trim());
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      ...style
    }
  }, parts.map((k, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: i
  }, i > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: '11px',
      fontFamily: 'var(--font-mono)'
    }
  }, "+"), /*#__PURE__*/React.createElement("kbd", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: '20px',
      padding: '3px 7px',
      borderRadius: '6px',
      background: 'var(--surface-inset)',
      border: '1px solid var(--border-soft)',
      borderBottomWidth: '2px',
      fontFamily: 'var(--font-mono)',
      fontSize: '11px',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-body)',
      lineHeight: 1
    }
  }, k))));
}
Object.assign(__ds_scope, { Kbd });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/companion/Kbd.jsx", error: String((e && e.message) || e) }); }

// components/companion/MoodMeter.jsx
try { (() => {
const LABELS = {
  1: 'Resting',
  2: 'Calm',
  3: 'Content',
  4: 'Warm',
  5: 'Delighted'
};
const COLORS = {
  1: 'var(--mood-1)',
  2: 'var(--mood-2)',
  3: 'var(--mood-3)',
  4: 'var(--mood-4)',
  5: 'var(--mood-5)'
};

/**
 * Mood meter — Aria's brain tracks mood on a 1–5 scale that decays in silence and
 * rises with engagement. Five seasonal pips + label. The brand's signature read-out.
 */
function MoodMeter({
  mood = 3,
  showLabel = true,
  size = 'md',
  style = {}
}) {
  const m = Math.max(1, Math.min(5, Math.round(mood)));
  const dot = size === 'sm' ? 10 : size === 'lg' ? 18 : 14;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      gap: size === 'sm' ? '5px' : '7px',
      alignItems: 'center'
    }
  }, [1, 2, 3, 4, 5].map(i => {
    const on = i <= m;
    return /*#__PURE__*/React.createElement("span", {
      key: i,
      style: {
        width: dot,
        height: dot,
        borderRadius: '50%',
        background: on ? COLORS[i] : 'transparent',
        border: on ? 'none' : '1.5px solid var(--border-soft)',
        boxShadow: on && i === m ? '0 0 10px ' + COLORS[i] : 'none',
        transition: 'all .3s ease'
      }
    });
  })), showLabel && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: size === 'sm' ? '11px' : '12px',
      letterSpacing: '.08em',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, LABELS[m], " ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: COLORS[m]
    }
  }, m, ".0")));
}
Object.assign(__ds_scope, { MoodMeter });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/companion/MoodMeter.jsx", error: String((e && e.message) || e) }); }

// components/companion/SpeechBubble.jsx
try { (() => {
/**
 * Aria's speech bubble — warm washi paper, soft ink hairline, downward tail toward
 * her, sumi-ink text, optional typewriter reveal (~3 chars / 22ms).
 */
function SpeechBubble({
  children,
  text = null,
  typewriter = false,
  tail = true,
  style = {}
}) {
  const full = text != null ? text : typeof children === 'string' ? children : '';
  const [shown, setShown] = React.useState(typewriter && full ? '' : full);
  React.useEffect(() => {
    if (!typewriter || !full) {
      setShown(full);
      return;
    }
    setShown('');
    let n = 0;
    const id = setInterval(() => {
      n = Math.min(n + 3, full.length);
      setShown(full.slice(0, n));
      if (n >= full.length) clearInterval(id);
    }, 22);
    return () => clearInterval(id);
  }, [full, typewriter]);
  const content = text != null || typeof children === 'string' ? shown : children;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      maxWidth: '320px',
      display: 'inline-block',
      background: 'var(--surface-bubble)',
      border: '1px solid var(--border-soft)',
      borderRadius: 'var(--radius-bubble)',
      boxShadow: 'var(--shadow-bubble)',
      padding: '14px 18px',
      fontFamily: 'var(--font-soft)',
      fontSize: 'var(--text-base)',
      fontWeight: 'var(--weight-medium)',
      lineHeight: 'var(--leading-snug)',
      color: 'var(--text-strong)',
      ...style
    }
  }, content, tail && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      left: '50%',
      bottom: '-9px',
      transform: 'translateX(-50%)',
      width: 0,
      height: 0,
      borderLeft: '10px solid transparent',
      borderRight: '10px solid transparent',
      borderTop: '10px solid var(--surface-bubble)',
      filter: 'drop-shadow(0 1px 0 var(--border-soft))'
    }
  }));
}
Object.assign(__ds_scope, { SpeechBubble });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/companion/SpeechBubble.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
const TONES = {
  maple: {
    bg: 'rgba(164,80,46,.12)',
    fg: 'var(--momiji-600)',
    bd: 'rgba(164,80,46,.30)'
  },
  matcha: {
    bg: 'rgba(111,123,74,.14)',
    fg: 'var(--matcha-500)',
    bd: 'rgba(111,123,74,.32)'
  },
  gold: {
    bg: 'rgba(232,185,107,.18)',
    fg: 'var(--wood-600)',
    bd: 'rgba(232,185,107,.45)'
  },
  sora: {
    bg: 'rgba(124,151,168,.16)',
    fg: 'var(--sora-500)',
    bd: 'rgba(124,151,168,.35)'
  },
  sakura: {
    bg: 'rgba(228,134,160,.16)',
    fg: 'var(--sakura-500)',
    bd: 'rgba(228,134,160,.36)'
  },
  vermilion: {
    bg: 'rgba(217,79,42,.13)',
    fg: 'var(--shu-600)',
    bd: 'rgba(217,79,42,.32)'
  },
  neutral: {
    bg: 'var(--surface-inset)',
    fg: 'var(--text-muted)',
    bd: 'var(--border-soft)'
  }
};

/** Small categorical badge — bug categories, tags, counts. */
function Badge({
  tone = 'neutral',
  icon = null,
  children,
  style = {}
}) {
  const t = TONES[tone] || TONES.neutral;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      padding: '3px 9px',
      borderRadius: 'var(--radius-sm)',
      background: t.bg,
      color: t.fg,
      border: '1px solid ' + t.bd,
      fontFamily: 'var(--font-mono)',
      fontSize: '11px',
      fontWeight: 'var(--weight-medium)',
      letterSpacing: '.03em',
      ...style
    }
  }, icon && /*#__PURE__*/React.createElement("span", null, icon), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const SIZES = {
  sm: {
    padding: '6px 12px',
    fontSize: 'var(--text-sm)',
    radius: 'var(--radius-sm)',
    gap: '6px'
  },
  md: {
    padding: '9px 18px',
    fontSize: 'var(--text-base)',
    radius: 'var(--radius-sm)',
    gap: '8px'
  },
  lg: {
    padding: '12px 24px',
    fontSize: 'var(--text-md)',
    radius: 'var(--radius-md)',
    gap: '10px'
  }
};

/**
 * Aria primary button. Maple fill is the warm accent; ghost/secondary
 * sit on warm paper. Hover warms, press deepens — never shrink.
 */
function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  fullWidth = false,
  icon = null,
  iconAfter = null,
  onClick,
  children,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  const s = SIZES[size] || SIZES.md;
  const palette = {
    primary: {
      bg: press ? 'var(--primary-press)' : hover ? 'var(--primary-hover)' : 'var(--primary)',
      color: 'var(--on-primary)',
      border: '1px solid transparent',
      shadow: hover ? '0 6px 18px rgba(164,80,46,.34)' : '0 3px 10px rgba(164,80,46,.22)'
    },
    secondary: {
      bg: hover ? 'var(--surface-active)' : 'var(--surface-card)',
      color: 'var(--text-strong)',
      border: '1px solid var(--border-soft)',
      shadow: hover ? 'var(--shadow-sm)' : 'var(--shadow-xs)'
    },
    ghost: {
      bg: hover ? 'var(--surface-hover)' : 'transparent',
      color: 'var(--text-link)',
      border: '1px solid transparent',
      shadow: 'none'
    },
    danger: {
      bg: hover ? 'var(--shu-400)' : 'var(--danger)',
      color: '#fff',
      border: '1px solid transparent',
      shadow: hover ? '0 6px 18px rgba(217,79,42,.34)' : 'none'
    }
  }[variant] || {};
  return /*#__PURE__*/React.createElement("button", _extends({
    onClick: disabled ? undefined : onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setPress(false);
    },
    onMouseDown: () => setPress(true),
    onMouseUp: () => setPress(false),
    disabled: disabled,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: s.gap,
      fontFamily: 'var(--font-ui)',
      fontWeight: 'var(--weight-bold)',
      fontSize: s.fontSize,
      padding: s.padding,
      borderRadius: s.radius,
      cursor: disabled ? 'not-allowed' : 'pointer',
      background: palette.bg,
      color: palette.color,
      border: palette.border,
      boxShadow: palette.shadow,
      opacity: disabled ? 0.45 : 1,
      width: fullWidth ? '100%' : 'auto',
      transition: 'background .15s ease, box-shadow .15s ease',
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      fontSize: '1.1em'
    }
  }, icon), children, iconAfter && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      fontSize: '1.1em'
    }
  }, iconAfter));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Metric.jsx
try { (() => {
/** Big metric readout — label + value (memory entries, mood, uptime, etc.). */
function Metric({
  label,
  value,
  unit = null,
  sub = null,
  tone = 'default',
  style = {}
}) {
  const valueColor = {
    default: 'var(--text-strong)',
    blue: 'var(--sora-500)',
    green: 'var(--matcha-500)',
    amber: 'var(--gold-400)',
    coral: 'var(--shu-500)',
    maple: 'var(--momiji-500)'
  }[tone] || 'var(--text-strong)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-ui)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-xs)',
      letterSpacing: 'var(--tracking-label)',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      marginBottom: 'var(--space-2)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: '6px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontWeight: 'var(--weight-bold)',
      fontSize: 'var(--text-2xl)',
      lineHeight: 1,
      color: valueColor
    }
  }, value), unit && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-md)',
      color: 'var(--text-muted)',
      fontFamily: 'var(--font-mono)'
    }
  }, unit)), sub && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginTop: 'var(--space-1)'
    }
  }, sub));
}
Object.assign(__ds_scope, { Metric });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Metric.jsx", error: String((e && e.message) || e) }); }

// components/core/PaperPanel.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Washi-paper panel — the warm, softly-shadowed base container for everything. */
function PaperPanel({
  title = null,
  icon = null,
  aura = false,
  mood = 3,
  padding = 'var(--space-5)',
  children,
  style = {},
  ...rest
}) {
  const auraShadow = aura ? `var(--aura-${Math.max(1, Math.min(5, Math.round(mood)))})` : 'var(--shadow-card)';
  return /*#__PURE__*/React.createElement("section", _extends({
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: auraShadow,
      padding,
      color: 'var(--text-body)',
      ...style
    }
  }, rest), title && /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      marginBottom: 'var(--space-4)'
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '1.15em'
    }
  }, icon), /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-display)',
      fontWeight: 'var(--weight-semibold)',
      fontSize: 'var(--text-md)',
      color: 'var(--text-strong)',
      letterSpacing: 'var(--tracking-tight)'
    }
  }, title)), children);
}
Object.assign(__ds_scope, { PaperPanel });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/PaperPanel.jsx", error: String((e && e.message) || e) }); }

// components/core/Select.jsx
try { (() => {
/** Styled dropdown — the dashboard's "Core Neural Profiles" model pickers. */
function Select({
  value,
  onChange,
  options = [],
  label = null,
  disabled = false,
  style = {}
}) {
  const id = React.useId();
  const opts = options.map(o => typeof o === 'string' ? {
    value: o,
    label: o
  } : o);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-ui)',
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: id,
    style: {
      display: 'block',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      marginBottom: 'var(--space-2)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("select", {
    id: id,
    value: value,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    style: {
      width: '100%',
      appearance: 'none',
      WebkitAppearance: 'none',
      MozAppearance: 'none',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      background: 'var(--surface-inset)',
      border: '1px solid var(--border-soft)',
      borderRadius: 'var(--radius-sm)',
      padding: '10px 36px 10px 12px',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      outline: 'none'
    }
  }, opts.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value,
    style: {
      background: 'var(--washi-50)',
      color: 'var(--text-body)'
    }
  }, o.label))), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      right: '12px',
      top: '50%',
      transform: 'translateY(-50%)',
      pointerEvents: 'none',
      color: 'var(--momiji-500)',
      fontSize: '12px'
    }
  }, "\u25BE")));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Select.jsx", error: String((e && e.message) || e) }); }

// components/core/Slider.jsx
try { (() => {
/** Range slider — voice volume, mood-decay rate, scan cadence. Maple fill + soft thumb. */
function Slider({
  value = 50,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  label = null,
  format = v => v,
  disabled = false,
  style = {}
}) {
  const pct = (value - min) / (max - min) * 100;
  const id = React.useId();
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-ui)',
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      marginBottom: 'var(--space-2)'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: id,
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--momiji-500)'
    }
  }, format(value))), /*#__PURE__*/React.createElement("input", {
    id: id,
    type: "range",
    min: min,
    max: max,
    step: step,
    value: value,
    disabled: disabled,
    onChange: e => onChange && onChange(Number(e.target.value)),
    style: {
      width: '100%',
      height: '6px',
      borderRadius: 'var(--radius-pill)',
      appearance: 'none',
      WebkitAppearance: 'none',
      outline: 'none',
      cursor: disabled ? 'not-allowed' : 'pointer',
      background: `linear-gradient(to right, var(--primary) 0%, var(--primary) ${pct}%, var(--surface-inset) ${pct}%, var(--surface-inset) 100%)`,
      opacity: disabled ? 0.5 : 1
    }
  }), /*#__PURE__*/React.createElement("style", null, `
        input[type=range]::-webkit-slider-thumb{ -webkit-appearance:none; width:18px; height:18px;
          border-radius:50%; background:var(--washi-50); border:3px solid var(--primary);
          box-shadow:0 1px 5px rgba(74,46,28,.35); cursor:pointer; }
        input[type=range]::-moz-range-thumb{ width:18px; height:18px; border-radius:50%; background:var(--washi-50);
          border:3px solid var(--primary); box-shadow:0 1px 5px rgba(74,46,28,.35); cursor:pointer; }
      `));
}
Object.assign(__ds_scope, { Slider });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Slider.jsx", error: String((e && e.message) || e) }); }

// components/core/StatusPill.jsx
try { (() => {
const TONES = {
  online: {
    c: 'var(--success)',
    t: 'Online'
  },
  offline: {
    c: 'var(--danger)',
    t: 'Offline'
  },
  idle: {
    c: 'var(--sora-400)',
    t: 'Resting'
  },
  listen: {
    c: 'var(--sora-500)',
    t: 'Listening'
  },
  think: {
    c: 'var(--warning)',
    t: 'Thinking'
  },
  speak: {
    c: 'var(--momiji-400)',
    t: 'Speaking'
  },
  neutral: {
    c: 'var(--sumi-400)',
    t: ''
  }
};

/** Status pill — a soft dot + label. Encodes service / companion state by hue. */
function StatusPill({
  status = 'idle',
  children,
  pulse = false,
  style = {}
}) {
  const tone = TONES[status] || TONES.neutral;
  const label = children != null ? children : tone.t;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      padding: '5px 12px 5px 10px',
      borderRadius: 'var(--radius-pill)',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-soft)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-medium)',
      letterSpacing: '.04em',
      color: 'var(--text-body)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      background: tone.c,
      flexShrink: 0,
      boxShadow: '0 0 7px ' + tone.c,
      animation: pulse ? 'aria-pulse 1.8s ease-in-out infinite' : 'none'
    }
  }), label, /*#__PURE__*/React.createElement("style", null, '@keyframes aria-pulse{0%,100%{opacity:1}50%{opacity:.35}}'));
}
Object.assign(__ds_scope, { StatusPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/StatusPill.jsx", error: String((e && e.message) || e) }); }

// components/core/Toggle.jsx
try { (() => {
/** On/off switch — Aria's settings toggles (sleep, autostart, voice). */
function Toggle({
  checked = false,
  onChange,
  label = null,
  disabled = false,
  style = {}
}) {
  const toggle = () => {
    if (!disabled && onChange) onChange(!checked);
  };
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      fontFamily: 'var(--font-ui)',
      fontSize: 'var(--text-base)',
      color: 'var(--text-body)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    role: "switch",
    "aria-checked": checked,
    onClick: toggle,
    style: {
      position: 'relative',
      width: '44px',
      height: '24px',
      borderRadius: 'var(--radius-pill)',
      background: checked ? 'var(--primary)' : 'var(--surface-sunken)',
      border: '1px solid ' + (checked ? 'transparent' : 'var(--border-soft)'),
      boxShadow: checked ? '0 0 12px rgba(164,80,46,.40)' : 'var(--shadow-inset)',
      transition: 'background .18s ease, box-shadow .18s ease',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: '2px',
      left: checked ? '21px' : '2px',
      width: '19px',
      height: '19px',
      borderRadius: '50%',
      background: checked ? 'var(--washi-50)' : 'var(--washi-50)',
      transition: 'left .18s cubic-bezier(.4,1.3,.6,1)',
      boxShadow: '0 1px 3px rgba(74,46,28,.35)'
    }
  })), label && /*#__PURE__*/React.createElement("span", null, label));
}
Object.assign(__ds_scope, { Toggle });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Toggle.jsx", error: String((e && e.message) || e) }); }

// ui_kits/chat_window/chat.jsx
try { (() => {
/* Aria — chat window. The hero surface: talk to her, watch her mood drift.
   Composes design-system primitives from the bundle. Mounts to #root. */
const NS = window.AstroBudDesignSystem_8da794;
const {
  AriaAvatar,
  MoodMeter,
  SpeechBubble,
  Button,
  Badge,
  StatusPill,
  Kbd,
  Metric
} = NS;
const {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakSlider,
  TweakToggle,
  TweakText,
  TweakColor
} = window;
const AV = 'aria-avatar-round.png'; // resolved relative to index.html (see kit README)

/* --- Aria's canned, mood-aware replies (faux brain) ---------------------- */
function ariaReply(text, mood) {
  const t = text.toLowerCase();
  if (/\b(hi|hello|hey|good morning|ただいま)\b/.test(t)) return mood >= 4 ? "There you are. I was hoping you'd come back." : "Hey. Welcome back.";
  if (t.includes('?')) return mood >= 4 ? "Mm — I think so, but tell me what *you* think first." : "Good question. Give me a second to actually think about it.";
  if (/\b(tired|sad|stressed|hard day|exhausted)\b/.test(t)) return "Then stop for a minute. The work will still be there. I'll be here too.";
  if (/\b(thanks|thank you|love)\b/.test(t)) return "…You don't have to thank me. But I'll take it. 🌸";
  if (/\b(maple|autumn|fall|leaves|kyoto)\b/.test(t)) return "The maples are early this year. We should go look while they last.";
  return mood >= 4 ? "I like that you tell me these things." : "Noted. I'll remember that.";
}
const MOOD_DELTA = text => {
  const t = text.toLowerCase();
  if (t.includes('?')) return 0.5;
  if (/\b(thanks|thank you|love|good|happy|nice)\b/.test(t)) return 0.5;
  if (/\b(stupid|shut up|hate|annoying)\b/.test(t)) return -1;
  return 0.25;
};
function TitleBar({
  mood
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      padding: '10px 14px',
      borderBottom: '1px solid var(--border-hairline)',
      background: 'var(--surface-panel)',
      borderTopLeftRadius: 'var(--radius-lg)',
      borderTopRightRadius: 'var(--radius-lg)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: '7px'
    }
  }, ['#E2653C', '#E8B96B', '#8C9A5E'].map(c => /*#__PURE__*/React.createElement("span", {
    key: c,
    style: {
      width: 11,
      height: 11,
      borderRadius: '50%',
      background: c
    }
  }))), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontWeight: 700,
      fontSize: '14px',
      color: 'var(--text-strong)',
      marginLeft: '4px'
    }
  }, "Aria"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 'auto'
    }
  }, /*#__PURE__*/React.createElement(MoodMeter, {
    mood: mood,
    size: "sm"
  })));
}
function SidePanel({
  mood,
  float = true
}) {
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: '210px',
      flexShrink: 0,
      padding: '22px 18px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '16px',
      borderRight: '1px solid var(--border-hairline)',
      background: 'var(--bg-elevated)'
    }
  }, /*#__PURE__*/React.createElement(AriaAvatar, {
    src: AV,
    mood: mood,
    size: 120,
    float: float
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-display)',
      fontWeight: 700,
      fontSize: '20px',
      color: 'var(--text-strong)'
    }
  }, "Aria"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: '10px',
      letterSpacing: '.16em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      marginTop: '3px'
    }
  }, "local \xB7 offline")), /*#__PURE__*/React.createElement(StatusPill, {
    status: "online"
  }, "Listening"), /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      borderTop: '1px solid var(--border-hairline)',
      paddingTop: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
    }
  }, /*#__PURE__*/React.createElement(Metric, {
    label: "Memories",
    value: "1,284",
    tone: "maple",
    sub: "episodic + facts"
  }), /*#__PURE__*/React.createElement(Metric, {
    label: "Days together",
    value: "46",
    tone: "blue"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 'auto',
      display: 'flex',
      gap: '6px',
      flexWrap: 'wrap',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "maple",
    icon: "\uD83C\uDF41"
  }, "autumn"), /*#__PURE__*/React.createElement(Badge, {
    tone: "matcha"
  }, "curious")));
}
function Bubble({
  from,
  text,
  typewriter
}) {
  const mine = from === 'me';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: mine ? 'flex-end' : 'flex-start'
    }
  }, mine ? /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: '76%',
      background: 'var(--primary)',
      color: 'var(--on-primary)',
      fontFamily: 'var(--font-soft)',
      fontWeight: 500,
      fontSize: 'var(--text-base)',
      padding: '11px 15px',
      borderRadius: '20px 20px 6px 20px',
      boxShadow: 'var(--shadow-sm)',
      lineHeight: 1.45
    }
  }, text) : /*#__PURE__*/React.createElement(SpeechBubble, {
    tail: false,
    text: text,
    typewriter: typewriter,
    style: {
      borderRadius: '20px 20px 20px 6px',
      maxWidth: '76%'
    }
  }));
}
function App() {
  const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
    "startMood": 3,
    "accent": "#A4502E",
    "floatAvatar": true,
    "greeting": "\u305f\u3060\u3044\u307e \u2014 welcome back. I kept your place."
  } /*EDITMODE-END*/;
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [mood, setMood] = React.useState(t.startMood);
  const [msgs, setMsgs] = React.useState([{
    from: 'aria',
    text: t.greeting
  }]);
  const [draft, setDraft] = React.useState('');
  const scroller = React.useRef(null);

  // keep opening message + mood in sync with tweaks before the user has chatted
  React.useEffect(() => {
    if (msgs.length <= 1) setMood(t.startMood);
  }, [t.startMood]);
  React.useEffect(() => {
    setMsgs(m => m.length <= 1 ? [{
      from: 'aria',
      text: t.greeting
    }] : m);
  }, [t.greeting]);
  React.useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [msgs]);
  const send = () => {
    const text = draft.trim();
    if (!text) return;
    const nextMood = Math.max(1, Math.min(5, mood + MOOD_DELTA(text)));
    setMsgs(m => [...m, {
      from: 'me',
      text
    }]);
    setDraft('');
    setTimeout(() => {
      setMood(nextMood);
      setMsgs(m => [...m, {
        from: 'aria',
        text: ariaReply(text, nextMood),
        typewriter: true
      }]);
    }, 480);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: '720px',
      height: '560px',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface-card)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-pop)',
      overflow: 'hidden',
      border: '1px solid var(--border-soft)',
      '--primary': t.accent
    }
  }, /*#__PURE__*/React.createElement(TitleBar, {
    mood: Math.round(mood)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(SidePanel, {
    mood: Math.round(mood),
    float: t.floatAvatar
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    ref: scroller,
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      backgroundImage: 'radial-gradient(circle at 100% 0%, rgba(232,185,107,.16), transparent 55%)'
    }
  }, msgs.map((m, i) => /*#__PURE__*/React.createElement(Bubble, {
    key: i,
    from: m.from,
    text: m.text,
    typewriter: m.typewriter
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      padding: '14px 16px',
      borderTop: '1px solid var(--border-hairline)',
      background: 'var(--bg-elevated)'
    }
  }, /*#__PURE__*/React.createElement("input", {
    value: draft,
    onChange: e => setDraft(e.target.value),
    onKeyDown: e => {
      if (e.key === 'Enter') send();
    },
    placeholder: "Say something to Aria\u2026",
    style: {
      flex: 1,
      border: '1px solid var(--border-soft)',
      borderRadius: 'var(--radius-pill)',
      padding: '11px 16px',
      fontFamily: 'var(--font-ui)',
      fontSize: 'var(--text-base)',
      color: 'var(--text-strong)',
      background: 'var(--surface-card)',
      outline: 'none'
    }
  }), /*#__PURE__*/React.createElement("span", {
    title: "Push to talk",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '42px',
      height: '42px',
      borderRadius: '50%',
      background: 'var(--surface-inset)',
      border: '1px solid var(--border-soft)',
      cursor: 'pointer',
      fontSize: '18px'
    }
  }, "\uD83C\uDFB4"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    onClick: send,
    iconAfter: "\u2192"
  }, "Send")))), /*#__PURE__*/React.createElement(TweaksPanel, null, /*#__PURE__*/React.createElement(TweakSection, {
    label: "Aria"
  }), /*#__PURE__*/React.createElement(TweakSlider, {
    label: "Starting mood",
    value: t.startMood,
    min: 1,
    max: 5,
    step: 1,
    onChange: v => setTweak('startMood', v)
  }), /*#__PURE__*/React.createElement(TweakToggle, {
    label: "Avatar floats",
    value: t.floatAvatar,
    onChange: v => setTweak('floatAvatar', v)
  }), /*#__PURE__*/React.createElement(TweakText, {
    label: "Opening line",
    value: t.greeting,
    onChange: v => setTweak('greeting', v)
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "Accent"
  }), /*#__PURE__*/React.createElement(TweakColor, {
    label: "Accent",
    value: t.accent,
    options: ['#A4502E', '#D94F2A', '#E486A0', '#6F7B4A'],
    onChange: v => setTweak('accent', v)
  })));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/chat_window/chat.jsx", error: String((e && e.message) || e) }); }

// ui_kits/chat_window/tweaks-panel.jsx
try { (() => {
// @ds-adherence-ignore -- omelette starter scaffold (raw elements/hex/px by design)

/* BEGIN USAGE */
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
// Exports (to window): useTweaks, TweaksPanel, TweakSection, TweakRow, TweakSlider,
//   TweakToggle, TweakRadio, TweakSelect, TweakText, TweakNumber, TweakColor, TweakButton.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// TweakRadio is the segmented control for 2–3 short options (auto-falls-back to
// TweakSelect past ~16/~10 chars per label); reach for TweakSelect directly when
// options are many or long. For color tweaks always curate 3-4 options rather than
// a free picker; an option can also be a whole 2–5 color palette (the stored value
// is the array). The Tweak* controls are a floor, not a ceiling — build custom
// controls inside the panel if a tweak calls for UI they don't cover.
/* END USAGE */
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null ? keyOrEdits : {
      [keyOrEdits]: val
    };
    setValues(prev => ({
      ...prev,
      ...edits
    }));
    window.parent.postMessage({
      type: '__edit_mode_set_keys',
      edits
    }, '*');
    // Same-window signal so in-page listeners (deck-stage rail thumbnails)
    // can react — the parent message only reaches the host, not peers.
    window.dispatchEvent(new CustomEvent('tweakchange', {
      detail: edits
    }));
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({
  title = 'Tweaks',
  children
}) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({
    x: 16,
    y: 16
  });
  const PAD = 16;
  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth,
      h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y))
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);
  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);
  React.useEffect(() => {
    const onMsg = e => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({
      type: '__edit_mode_available'
    }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);
  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({
      type: '__edit_mode_dismissed'
    }, '*');
  };
  const onDragStart = e => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX,
      sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = ev => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy)
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("style", null, __TWEAKS_STYLE), /*#__PURE__*/React.createElement("div", {
    ref: dragRef,
    className: "twk-panel",
    "data-omelette-chrome": "",
    style: {
      right: offsetRef.current.x,
      bottom: offsetRef.current.y
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-hd",
    onMouseDown: onDragStart
  }, /*#__PURE__*/React.createElement("b", null, title), /*#__PURE__*/React.createElement("button", {
    className: "twk-x",
    "aria-label": "Close tweaks",
    onMouseDown: e => e.stopPropagation(),
    onClick: dismiss
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "twk-body"
  }, children)));
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "twk-sect"
  }, label), children);
}
function TweakRow({
  label,
  value,
  children,
  inline = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: inline ? 'twk-row twk-row-h' : 'twk-row'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label), value != null && /*#__PURE__*/React.createElement("span", {
    className: "twk-val"
  }, value)), children);
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label,
    value: `${value}${unit}`
  }, /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "twk-slider",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => onChange(Number(e.target.value))
  }));
}
function TweakToggle({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "twk-toggle",
    "data-on": value ? '1' : '0',
    role: "switch",
    "aria-checked": !!value,
    onClick: () => onChange(!value)
  }, /*#__PURE__*/React.createElement("i", null)));
}
function TweakRadio({
  label,
  value,
  options,
  onChange
}) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;

  // Segments wrap mid-word once per-segment width runs out. The track is
  // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
  // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
  // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
  // back to a dropdown rather than wrap.
  const labelLen = o => String(typeof o === 'object' ? o.label : o).length;
  const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
  const fitsAsSegments = maxLen <= ({
    2: 16,
    3: 10
  }[options.length] ?? 0);
  if (!fitsAsSegments) {
    // <select> emits strings — map back to the original option value so the
    // fallback stays type-preserving (numbers, booleans) like the segment path.
    const resolve = s => {
      const m = options.find(o => String(typeof o === 'object' ? o.value : o) === s);
      return m === undefined ? s : typeof m === 'object' ? m.value : m;
    };
    return /*#__PURE__*/React.createElement(TweakSelect, {
      label: label,
      value: value,
      options: options,
      onChange: s => onChange(resolve(s))
    });
  }
  const opts = options.map(o => typeof o === 'object' ? o : {
    value: o,
    label: o
  });
  const idx = Math.max(0, opts.findIndex(o => o.value === value));
  const n = opts.length;
  const segAt = clientX => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor((clientX - r.left - 2) / inner * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };
  const onPointerDown = e => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = ev => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    ref: trackRef,
    role: "radiogroup",
    onPointerDown: onPointerDown,
    className: dragging ? 'twk-seg dragging' : 'twk-seg'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-seg-thumb",
    style: {
      left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
      width: `calc((100% - 4px) / ${n})`
    }
  }), opts.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    type: "button",
    role: "radio",
    "aria-checked": o.value === value
  }, o.label))));
}
function TweakSelect({
  label,
  value,
  options,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("select", {
    className: "twk-field",
    value: value,
    onChange: e => onChange(e.target.value)
  }, options.map(o => {
    const v = typeof o === 'object' ? o.value : o;
    const l = typeof o === 'object' ? o.label : o;
    return /*#__PURE__*/React.createElement("option", {
      key: v,
      value: v
    }, l);
  })));
}
function TweakText({
  label,
  value,
  placeholder,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("input", {
    className: "twk-field",
    type: "text",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange
}) {
  const clamp = n => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({
    x: 0,
    val: 0
  });
  const onScrubStart = e => {
    e.preventDefault();
    startRef.current = {
      x: e.clientX,
      val: value
    };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = ev => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-num"
  }, /*#__PURE__*/React.createElement("span", {
    className: "twk-num-lbl",
    onPointerDown: onScrubStart
  }, label), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: value,
    min: min,
    max: max,
    step: step,
    onChange: e => onChange(clamp(Number(e.target.value)))
  }), unit && /*#__PURE__*/React.createElement("span", {
    className: "twk-num-unit"
  }, unit));
}

// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
  const h = String(hex).replace('#', '');
  const x = h.length === 3 ? h.replace(/./g, c => c + c) : h.padEnd(6, '0');
  const n = parseInt(x.slice(0, 6), 16);
  if (Number.isNaN(n)) return true;
  const r = n >> 16 & 255,
    g = n >> 8 & 255,
    b = n & 255;
  return r * 299 + g * 587 + b * 114 > 148000;
}
const __TwkCheck = ({
  light
}) => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 14 14",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 7.2 5.8 10 11 4.2",
  fill: "none",
  strokeWidth: "2.2",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  stroke: light ? 'rgba(0,0,0,.78)' : '#fff'
}));

// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({
  label,
  value,
  options,
  onChange
}) {
  if (!options || !options.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "twk-row twk-row-h"
    }, /*#__PURE__*/React.createElement("div", {
      className: "twk-lbl"
    }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("input", {
      type: "color",
      className: "twk-swatch",
      value: value,
      onChange: e => onChange(e.target.value)
    }));
  }
  // Native <input type=color> emits lowercase hex per the HTML spec, so
  // compare case-insensitively. String() guards JSON.stringify(undefined),
  // which returns the primitive undefined (no .toLowerCase).
  const key = o => String(JSON.stringify(o)).toLowerCase();
  const cur = key(value);
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-chips",
    role: "radiogroup"
  }, options.map((o, i) => {
    const colors = Array.isArray(o) ? o : [o];
    const [hero, ...rest] = colors;
    const sup = rest.slice(0, 4);
    const on = key(o) === cur;
    return /*#__PURE__*/React.createElement("button", {
      key: i,
      type: "button",
      className: "twk-chip",
      role: "radio",
      "aria-checked": on,
      "data-on": on ? '1' : '0',
      "aria-label": colors.join(', '),
      title: colors.join(' · '),
      style: {
        background: hero
      },
      onClick: () => onChange(o)
    }, sup.length > 0 && /*#__PURE__*/React.createElement("span", null, sup.map((c, j) => /*#__PURE__*/React.createElement("i", {
      key: j,
      style: {
        background: c
      }
    }))), on && /*#__PURE__*/React.createElement(__TwkCheck, {
      light: __twkIsLight(hero)
    }));
  })));
}
function TweakButton({
  label,
  onClick,
  secondary = false
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: secondary ? 'twk-btn secondary' : 'twk-btn',
    onClick: onClick
  }, label);
}
Object.assign(window, {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRow,
  TweakSlider,
  TweakToggle,
  TweakRadio,
  TweakSelect,
  TweakText,
  TweakNumber,
  TweakColor,
  TweakButton
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/chat_window/tweaks-panel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/control_matrix/dashboard.jsx
try { (() => {
/* Aria — Settings. Top bar, layout, mount. */
const NS = window.AstroBudDesignSystem_8da794;
const {
  Button,
  AriaAvatar
} = NS;
const {
  StatusCard,
  MemoryCard,
  MoodCard,
  VoiceCard,
  PersonaCard
} = window.ARIA_SETTINGS;
const AV = 'aria-avatar-round.png';
function Topbar({
  mood
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '14px',
      padding: '16px 30px',
      borderBottom: '1px solid var(--border-hairline)',
      background: 'var(--bg-elevated)',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }
  }, /*#__PURE__*/React.createElement(AriaAvatar, {
    src: AV,
    mood: mood,
    size: 40
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-display)',
      fontWeight: 700,
      fontSize: '22px',
      color: 'var(--text-strong)'
    }
  }, "Aria", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontWeight: 500,
      fontSize: '10px',
      letterSpacing: '.24em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      marginLeft: '12px'
    }
  }, "settings")));
}
function Toast({
  msg
}) {
  if (!msg) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      bottom: '24px',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 300,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-soft)',
      borderRadius: 'var(--radius-md)',
      padding: '12px 18px',
      color: 'var(--text-strong)',
      fontFamily: 'var(--font-ui)',
      fontSize: '14px',
      boxShadow: 'var(--shadow-pop)',
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    }
  }, "\uD83C\uDF41 ", msg);
}
function App() {
  const [toast, setToast] = React.useState('');
  const mood = 4;
  const fire = m => {
    setToast(m);
    clearTimeout(window.__art);
    window.__art = setTimeout(() => setToast(''), 2600);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100vh'
    }
  }, /*#__PURE__*/React.createElement(Topbar, {
    mood: mood
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      maxWidth: '1080px',
      margin: '0 auto',
      padding: '24px 30px 48px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '18px',
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '18px'
    }
  }, /*#__PURE__*/React.createElement(StatusCard, {
    mood: mood
  }), /*#__PURE__*/React.createElement(MemoryCard, null), /*#__PURE__*/React.createElement(MoodCard, null)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '18px'
    }
  }, /*#__PURE__*/React.createElement(VoiceCard, null), /*#__PURE__*/React.createElement(PersonaCard, null))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'center',
      marginTop: '28px'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "lg",
    icon: "\uD83C\uDF41",
    onClick: () => fire('Saved. Aria will remember.')
  }, "Save changes"))), /*#__PURE__*/React.createElement(Toast, {
    msg: toast
  }));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/control_matrix/dashboard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/control_matrix/panels.jsx
try { (() => {
/* Aria — Settings panel sections. Calm, plain, warm.
   Composes design-system primitives; attaches to window.ARIA_SETTINGS. */
const NS = window.AstroBudDesignSystem_8da794;
const {
  PaperPanel,
  Select,
  Toggle,
  Slider,
  Button,
  StatusPill,
  Badge,
  Metric,
  MoodMeter,
  Kbd
} = NS;
const microLabel = {
  fontFamily: 'var(--font-mono)',
  fontSize: '10px',
  letterSpacing: '.2em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)'
};

/* ---- Status ------------------------------------------------------------- */
function StatusCard({
  mood
}) {
  return /*#__PURE__*/React.createElement(PaperPanel, {
    title: "Aria",
    icon: "\uD83C\uDFEF",
    aura: true,
    mood: mood
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      marginBottom: '14px',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(StatusPill, {
    status: "online"
  }, "Listening"), /*#__PURE__*/React.createElement(MoodMeter, {
    mood: mood
  })), /*#__PURE__*/React.createElement("p", {
    style: {
      ...microLabel,
      margin: '0 0 8px'
    }
  }, "Running on"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '6px'
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "maple"
  }, "local LLM \xB7 :1010"), /*#__PURE__*/React.createElement(Badge, {
    tone: "matcha"
  }, "XTTS voice \xB7 :5003"), /*#__PURE__*/React.createElement(Badge, {
    tone: "sora"
  }, "ChromaDB \xB7 :8000")));
}

/* ---- Memory ------------------------------------------------------------- */
function MemoryCard() {
  return /*#__PURE__*/React.createElement(PaperPanel, {
    title: "Memory",
    icon: "\uD83C\uDF75"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '26px',
      marginBottom: '16px',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Metric, {
    label: "Episodic",
    value: "1,041",
    tone: "maple",
    sub: "conversations"
  }), /*#__PURE__*/React.createElement(Metric, {
    label: "Facts",
    value: "243",
    tone: "blue",
    sub: "about you"
  }), /*#__PURE__*/React.createElement(Metric, {
    label: "Reflections",
    value: "88",
    tone: "green",
    sub: "her own thoughts"
  })), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '13px',
      color: 'var(--text-muted)',
      margin: '0 0 12px',
      lineHeight: 1.5
    }
  }, "Aria keeps three kinds of memory. You can let one go if you'd like \u2014 she'll understand."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '10px',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    icon: "\uD83D\uDCD3"
  }, "Browse memories"), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    icon: "\uD83D\uDDD1\uFE0F"
  }, "Forget a thing\u2026")));
}

/* ---- Mood & reflection -------------------------------------------------- */
function MoodCard() {
  const [decay, setDecay] = React.useState(2);
  const [cadence, setCadence] = React.useState(120);
  return /*#__PURE__*/React.createElement(PaperPanel, {
    title: "Mood & reflection",
    icon: "\uD83C\uDF19"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '13px',
      color: 'var(--text-muted)',
      margin: '0 0 16px',
      lineHeight: 1.55
    }
  }, "Her mood drifts toward calm when the room is quiet, and warms when you talk with her. Reflections are the quiet thoughts she has on her own."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
    }
  }, /*#__PURE__*/React.createElement(Slider, {
    label: "Mood decay",
    value: decay,
    onChange: setDecay,
    min: 0,
    max: 5,
    step: 0.5,
    format: v => v + ' /hr'
  }), /*#__PURE__*/React.createElement(Slider, {
    label: "Reflection cadence",
    value: cadence,
    onChange: setCadence,
    min: 30,
    max: 240,
    step: 15,
    format: v => v + ' min'
  })));
}

/* ---- Voice -------------------------------------------------------------- */
function VoiceCard() {
  const [voice, setVoice] = React.useState('Aria (cloned)');
  const [vol, setVol] = React.useState(72);
  const [on, setOn] = React.useState(true);
  return /*#__PURE__*/React.createElement(PaperPanel, {
    title: "Voice",
    icon: "\uD83C\uDFB4"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
    }
  }, /*#__PURE__*/React.createElement(Toggle, {
    checked: on,
    onChange: setOn,
    label: "Speak replies aloud"
  }), /*#__PURE__*/React.createElement(Select, {
    label: "Voice model",
    value: voice,
    onChange: setVoice,
    options: ['Aria (cloned)', 'Soft', 'Bright', 'Whisper']
  }), /*#__PURE__*/React.createElement(Slider, {
    label: "Volume",
    value: vol,
    onChange: setVol,
    min: 0,
    max: 100,
    format: v => v + '%'
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      fontSize: '13px',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "Push to talk"), /*#__PURE__*/React.createElement(Kbd, null, "Ctrl+Shift+Space"))));
}

/* ---- Persona ------------------------------------------------------------ */
function PersonaCard() {
  const [model, setModel] = React.useState('Qwen3.6-27B (uncensored)');
  const [boot, setBoot] = React.useState(true);
  const [quiet, setQuiet] = React.useState(false);
  return /*#__PURE__*/React.createElement(PaperPanel, {
    title: "Persona & presence",
    icon: "\uD83C\uDF38"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
    }
  }, /*#__PURE__*/React.createElement(Select, {
    label: "Mind (chat model)",
    value: model,
    onChange: setModel,
    options: ['Qwen3.6-27B (uncensored)', 'Lexi-Llama-3-8B', 'Qwen2.5-3B (fast)']
  }), /*#__PURE__*/React.createElement(Toggle, {
    checked: boot,
    onChange: setBoot,
    label: "\uD83C\uDF05 Wake with Windows"
  }), /*#__PURE__*/React.createElement(Toggle, {
    checked: quiet,
    onChange: setQuiet,
    label: "\uD83C\uDF19 Quiet hours (22:00\u201308:00)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '14px',
      padding: '10px 12px',
      borderRadius: 'var(--radius-sm)',
      fontSize: '13px',
      fontFamily: 'var(--font-ui)',
      background: quiet ? 'rgba(124,151,168,.12)' : 'rgba(140,154,94,.14)',
      border: '1px solid ' + (quiet ? 'rgba(124,151,168,.3)' : 'rgba(140,154,94,.3)'),
      color: quiet ? 'var(--sora-500)' : 'var(--matcha-500)'
    }
  }, quiet ? 'Aria is resting. She won’t speak up until morning.' : 'Aria is present, and listening.'));
}
window.ARIA_SETTINGS = {
  StatusCard,
  MemoryCard,
  MoodCard,
  VoiceCard,
  PersonaCard
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/control_matrix/panels.jsx", error: String((e && e.message) || e) }); }

__ds_ns.AriaAvatar = __ds_scope.AriaAvatar;

__ds_ns.Kbd = __ds_scope.Kbd;

__ds_ns.MoodMeter = __ds_scope.MoodMeter;

__ds_ns.SpeechBubble = __ds_scope.SpeechBubble;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Metric = __ds_scope.Metric;

__ds_ns.PaperPanel = __ds_scope.PaperPanel;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Slider = __ds_scope.Slider;

__ds_ns.StatusPill = __ds_scope.StatusPill;

__ds_ns.Toggle = __ds_scope.Toggle;

})();
