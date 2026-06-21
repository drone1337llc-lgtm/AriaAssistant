/* Aria — Dashboard app. Top bar, layout, save. */
const NS = window.AstroBudDesignSystem_8da794;
const { Button, AriaAvatar } = NS;
const { StatusCard, MemoryCard, MoodCard, VoiceCard, PersonaCard } = window.ARIA_SETTINGS;
const AV = 'aria-avatar-round.png';

const BRAIN    = 'http://127.0.0.1:8770';
const LMSTUDIO = 'http://192.168.68.88:1010/v1';

/* Default model values — overridden once /api/defaults loads */
const DEFAULTS = {
  LM_STUDIO_CHAT_MODEL:   '',
  LM_STUDIO_PARSER_MODEL: '',
  LM_STUDIO_CODER_MODEL:  '',
  LM_STUDIO_VISION_MODEL: '',
  LM_STUDIO_EMBED_MODEL:  '',
};

function Topbar({ mood }) {
  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: '14px', padding: '16px 30px',
      borderBottom: '1px solid var(--border-hairline)', background: 'var(--bg-elevated)',
      position: 'sticky', top: 0, zIndex: 100,
    }}>
      <AriaAvatar src={AV} mood={mood} size={40} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '22px', color: 'var(--text-strong)' }}>
        Aria
        <span style={{
          fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: '10px',
          letterSpacing: '.24em', textTransform: 'uppercase',
          color: 'var(--text-muted)', marginLeft: '12px',
        }}>settings</span>
      </div>
    </header>
  );
}

function Toast({ msg, ok }) {
  if (!msg) return null;
  const bg    = ok ? 'var(--surface-card)' : 'rgba(200,60,60,.18)';
  const color = ok ? 'var(--text-strong)'  : '#e87070';
  return (
    <div style={{
      position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)', zIndex: 300,
      background: bg, border: '1px solid var(--border-soft)',
      borderRadius: 'var(--radius-md)', padding: '12px 18px', color,
      fontFamily: 'var(--font-ui)', fontSize: '14px', boxShadow: 'var(--shadow-pop)',
      display: 'flex', alignItems: 'center', gap: '8px',
    }}>
      {ok ? '🍁' : '⚠'} {msg}
    </div>
  );
}

function App() {
  const [toast,      setToast]      = React.useState('');
  const [toastOk,    setToastOk]    = React.useState(true);
  const [selections, setSelections] = React.useState(DEFAULTS);
  const [lmModels,   setLmModels]   = React.useState([]);
  const [lmErr,      setLmErr]      = React.useState(null);
  const [brainMood,  setBrainMood]  = React.useState(3);

  /* Load current model config from server + live model list */
  React.useEffect(() => {
    fetch('/api/defaults')
      .then(r => r.json())
      .then(d => setSelections(prev => ({ ...prev, ...d })))
      .catch(() => {});

    fetch(`${LMSTUDIO}/models`)
      .then(r => r.json())
      .then(d => setLmModels((d.data || []).map(m => m.id).sort()))
      .catch(e => setLmErr(String(e)));

    fetch(`${BRAIN}/health`)
      .then(r => r.json())
      .then(d => setBrainMood(d?.mood?.value ?? 3))
      .catch(() => {});
  }, []);

  const handleSelect = (envKey, value) => {
    setSelections(prev => ({ ...prev, [envKey]: value }));
  };

  const fire = (msg, ok = true) => {
    setToast(msg); setToastOk(ok);
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => setToast(''), 3000);
  };

  const handleSave = async () => {
    try {
      const r = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(selections),
      });
      if (r.ok) {
        fire('Saved. Restart the brain server to apply.');
      } else {
        const t = await r.text();
        fire(`Save failed: ${t}`, false);
      }
    } catch (e) {
      fire(`Save failed: ${e}`, false);
    }
  };

  return (
    <div style={{ minHeight: '100vh' }}>
      <Topbar mood={brainMood} />
      <main style={{ maxWidth: '1080px', margin: '0 auto', padding: '24px 30px 48px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px', alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <StatusCard />
            <MemoryCard />
            <MoodCard />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <VoiceCard />
            <PersonaCard
              onSelect={handleSelect}
              selections={selections}
              lmModels={lmModels}
              lmErr={lmErr}
            />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: '28px' }}>
          <Button variant="primary" size="lg" icon="🍁" onClick={handleSave}>
            Save changes
          </Button>
        </div>
      </main>
      <Toast msg={toast} ok={toastOk} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
