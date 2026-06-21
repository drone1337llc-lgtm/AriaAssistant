/* Aria — Settings panels with live API calls.
   Fetches from:
     http://127.0.0.1:8770  — Aria Brain (FastAPI, CORS open)
     http://192.168.68.88:1010/v1  — LM Studio (OpenAI-compatible)
   Saves via POST /api/save on this server → writes brain/.env
*/
const NS = window.AstroBudDesignSystem_8da794;
const { PaperPanel, Select, Toggle, Slider, Button, StatusPill, Badge, Metric, MoodMeter, Kbd } = NS;

const BRAIN   = 'http://127.0.0.1:8770';
const LMSTUDIO = 'http://192.168.68.88:1010/v1';
const TTS_BASE = 'http://127.0.0.1:5003';

const microLabel = {
  fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '.2em',
  textTransform: 'uppercase', color: 'var(--text-muted)',
};

/* ---- Shared hook: brain /health ----------------------------------------- */
function useBrainHealth() {
  const [data, setData] = React.useState(null);
  const [err,  setErr]  = React.useState(false);
  React.useEffect(() => {
    let cancelled = false;
    function poll() {
      fetch(`${BRAIN}/health`)
        .then(r => r.json())
        .then(d => { if (!cancelled) { setData(d); setErr(false); } })
        .catch(() => { if (!cancelled) setErr(true); });
    }
    poll();
    const id = setInterval(poll, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  return { data, err };
}

/* ---- Shared hook: LM Studio model list ---------------------------------- */
function useLMModels() {
  const [models, setModels] = React.useState([]);
  const [err, setErr] = React.useState(null);
  React.useEffect(() => {
    fetch(`${LMSTUDIO}/models`)
      .then(r => r.json())
      .then(d => setModels((d.data || []).map(m => m.id).sort()))
      .catch(e => setErr(String(e)));
  }, []);
  return { models, err };
}

/* ---- Status card --------------------------------------------------------- */
function StatusCard() {
  const { data, err } = useBrainHealth();
  const mood = data?.mood?.value ?? 3;
  const label = data?.mood?.label ?? (err ? 'offline' : '…');

  return (
    <PaperPanel title="Aria" icon="🏯" aura mood={mood}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <StatusPill status={err ? 'offline' : 'online'}>{err ? 'Offline' : 'Listening'}</StatusPill>
        <MoodMeter mood={mood} />
      </div>
      <p style={{ ...microLabel, margin: '0 0 8px' }}>Running on</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        <Badge tone={err ? 'sora' : 'maple'}>brain · :8770</Badge>
        <Badge tone="matcha">XTTS voice · :5003</Badge>
        <Badge tone="sora">LM Studio · :1010</Badge>
        <Badge tone="sora">ChromaDB · :8000</Badge>
      </div>
    </PaperPanel>
  );
}

/* ---- Memory card --------------------------------------------------------- */
function MemoryCard() {
  const { data } = useBrainHealth();
  const mem = data?.memory ?? {};
  const epi   = mem.episodic_count  ?? '—';
  const facts = mem.facts_count     ?? '—';
  const ref   = mem.thoughts_count  ?? '—';
  return (
    <PaperPanel title="Memory" icon="🍵">
      <div style={{ display: 'flex', gap: '26px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <Metric label="Episodic"    value={String(epi)}   tone="maple" sub="conversations" />
        <Metric label="Facts"       value={String(facts)}  tone="blue"  sub="about you" />
        <Metric label="Reflections" value={String(ref)}    tone="green" sub="her own thoughts" />
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: '0 0 12px', lineHeight: 1.5 }}>
        Aria keeps three kinds of memory. You can let one go if you'd like — she'll understand.
      </p>
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <Button variant="secondary" icon="📓">Browse memories</Button>
        <Button variant="danger"    icon="🗑️">Forget a thing…</Button>
      </div>
    </PaperPanel>
  );
}

/* ---- Mood & reflection card --------------------------------------------- */
function MoodCard() {
  const { data } = useBrainHealth();
  const moodVal  = data?.mood?.value  ?? 3;
  const idleHrs  = data?.mood?.hours_since_interaction ?? 0;
  const [decay,   setDecay]   = React.useState(2);
  const [cadence, setCadence] = React.useState(120);
  return (
    <PaperPanel title="Mood & reflection" icon="🌙">
      <div style={{ display: 'flex', gap: '20px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <Metric label="Current mood" value={moodVal.toFixed(1)} tone="maple" sub="/ 5" />
        <Metric label="Idle"         value={idleHrs.toFixed(1)} tone="blue"  sub="hours" />
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: '0 0 16px', lineHeight: 1.55 }}>
        Her mood drifts toward calm when the room is quiet, and warms when you talk with her.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <Slider label="Mood decay"        value={decay}   onChange={setDecay}   min={0} max={5}   step={0.5} format={v => v + ' /hr'} />
        <Slider label="Reflection cadence" value={cadence} onChange={setCadence} min={30} max={240} step={15}  format={v => v + ' min'} />
      </div>
    </PaperPanel>
  );
}

/* ---- Voice card ---------------------------------------------------------- */
function VoiceCard() {
  const [on,  setOn]  = React.useState(true);
  const [vol, setVol] = React.useState(72);
  return (
    <PaperPanel title="Voice" icon="🎴">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <Toggle checked={on} onChange={setOn} label="Speak replies aloud" />
        <Slider label="Volume" value={vol} onChange={setVol} min={0} max={100} format={v => v + '%'} />
        <div style={{ ...microLabel, margin: '4px 0 0' }}>TTS server · {TTS_BASE}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', color: 'var(--text-body)' }}>
          <span>Push to talk</span><Kbd>Ctrl+Shift+Space</Kbd>
        </div>
      </div>
    </PaperPanel>
  );
}

/* ---- Model role select helper ------------------------------------------- */
function ModelSelect({ label, envKey, currentValue, models, onChange }) {
  const opts = React.useMemo(() => {
    const list = [...models];
    if (currentValue && !list.includes(currentValue)) list.unshift(currentValue);
    return list.length ? list : [currentValue || '(none)'];
  }, [models, currentValue]);

  return (
    <Select
      label={label}
      value={currentValue || opts[0] || ''}
      onChange={v => onChange(envKey, v)}
      options={opts}
    />
  );
}

/* ---- Persona & models card ----------------------------------------------- */
function PersonaCard({ onSelect, selections, lmModels, lmErr }) {
  const [boot,  setBoot]  = React.useState(true);
  const [quiet, setQuiet] = React.useState(false);

  const ROLES = [
    { label: 'Mind (chat)',   key: 'LM_STUDIO_CHAT_MODEL'   },
    { label: 'Parser',        key: 'LM_STUDIO_PARSER_MODEL'  },
    { label: 'Coder',         key: 'LM_STUDIO_CODER_MODEL'   },
    { label: 'Vision',        key: 'LM_STUDIO_VISION_MODEL'  },
    { label: 'Embeddings',    key: 'LM_STUDIO_EMBED_MODEL'   },
  ];

  return (
    <PaperPanel title="Persona & models" icon="🌸">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {lmErr
          ? <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>⚠ LM Studio unreachable — using current config</p>
          : <p style={{ ...microLabel, marginBottom: '-4px' }}>{lmModels.length} models loaded · LM Studio :1010</p>
        }
        {ROLES.map(({ label, key }) => (
          <ModelSelect
            key={key}
            label={label}
            envKey={key}
            currentValue={selections[key] || ''}
            models={lmModels}
            onChange={onSelect}
          />
        ))}
        <Toggle checked={boot}  onChange={setBoot}  label="🌅 Wake with Windows" />
        <Toggle checked={quiet} onChange={setQuiet} label="🌙 Quiet hours (22:00–08:00)" />
      </div>
      <div style={{
        marginTop: '14px', padding: '10px 12px', borderRadius: 'var(--radius-sm)',
        fontSize: '13px', fontFamily: 'var(--font-ui)',
        background: quiet ? 'rgba(124,151,168,.12)' : 'rgba(140,154,94,.14)',
        border: '1px solid ' + (quiet ? 'rgba(124,151,168,.3)' : 'rgba(140,154,94,.3)'),
        color: quiet ? 'var(--sora-500)' : 'var(--matcha-500)',
      }}>
        {quiet ? 'Aria is resting. She won't speak up until morning.' : 'Aria is present, and listening.'}
      </div>
    </PaperPanel>
  );
}

window.ARIA_SETTINGS = { StatusCard, MemoryCard, MoodCard, VoiceCard, PersonaCard };
