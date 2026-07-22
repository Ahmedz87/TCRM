import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from './api';
import { TicketModal } from './Ticket';

type Msg = { role: 'user' | 'assistant'; content: string; image?: string };

const GOLD = '#F8500A';

export default function PortalChat() {
  const [open, setOpen]         = useState(false);
  const [aiNote, setAiNote]     = useState(false);
  const [configured, setConfig] = useState<boolean | null>(null);
  const [msgs, setMsgs]         = useState<Msg[]>([]);
  const [input, setInput]       = useState('');
  const [busy, setBusy]         = useState(false);
  const [typing, setTyping]     = useState(false);
  const [suggest, setSuggest]   = useState<string[]>([]);
  // ticket #88 — single image attachment for the current turn (vision)
  const [imgData, setImgData]   = useState<string | null>(null);   // data:image/...;base64,XXXX
  const [imgType, setImgType]   = useState<string>('');            // MIME, e.g. image/png
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const onPickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (e.target) e.target.value = '';   // allow re-picking the same file
    if (!f) return;
    if (!f.type.startsWith('image/')) return;
    if (f.size > 7 * 1024 * 1024) { alert('That image is too large (max 7 MB). Please pick a smaller screenshot.'); return; }
    const reader = new FileReader();
    reader.onload = () => { setImgData(String(reader.result)); setImgType(f.type); };
    reader.readAsDataURL(f);
  };
  const clearImage = () => { setImgData(null); setImgType(''); };

  useEffect(() => {
    apiGet('/portal/chat/health').then((r: any) => setConfig(!!r?.configured)).catch(() => setConfig(false));
    apiGet('/portal/chat/suggestions').then((r: any) => setSuggest(r?.suggestions || [])).catch(() => {});
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, typing, open]);

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

  const send = async (textArg?: string) => {
    const text = (textArg ?? input).trim();
    const hasImg = !!imgData;
    if ((!text && !hasImg) || busy) return;
    const userMsg: Msg = { role: 'user', content: text || (hasImg ? '📷 (image)' : ''), ...(hasImg ? { image: imgData! } : {}) };
    const next: Msg[] = [...msgs, userMsg];
    setMsgs(next);
    setInput('');
    // capture & clear the attachment for THIS turn
    const sendImg = imgData, sendType = imgType;
    clearImage();
    setBusy(true);
    setTyping(true);

    // the API history must not carry our local `image` display field
    const apiMessages = next.map(m => ({ role: m.role, content: m.content }));

    let parts: string[] = [];
    try {
      const body: any = { messages: apiMessages };
      if (sendImg) { body.image_b64 = sendImg; body.image_media_type = sendType || 'image/png'; }
      const r: any = await apiPost('/portal/chat', body);
      if (Array.isArray(r?.parts) && r.parts.length) parts = r.parts;
      else parts = [r?.reply || r?.detail || 'Sorry, something went wrong. Please try again.'];
    } catch {
      parts = ['Network error — please try again. 🙏'];
    }

    let acc = next;
    for (let i = 0; i < parts.length; i++) {
      const len = parts[i].length;
      // first bubble appears quickly (we already waited for the model);
      // each later bubble gets a longer "typing…" pause so they arrive one by one
      const delay = i === 0
        ? Math.min(1200, 300 + len * 12)
        : Math.min(4500, 1000 + (i - 1) * 700 + len * 12);
      setTyping(true);
      await sleep(delay);
      setTyping(false);
      acc = [...acc, { role: 'assistant', content: parts[i] }];
      setMsgs(acc);
      await sleep(180);
    }
    setBusy(false);
  };

  if (configured === false) return null;

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} title="Ask TNFX Assistant"
          style={{ position:'fixed', right:24, bottom:24, zIndex:9999, height:56, padding:'0 20px',
            borderRadius:28, border:'none', cursor:'pointer',
            background:'linear-gradient(135deg,#F8500A,#C77B45)', color:'#0B0E14', fontWeight:800,
            fontSize:15, fontFamily:'inherit', boxShadow:'0 8px 26px rgba(232,184,75,0.45)',
            display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:20 }}>💬</span> Ask TNFX
        </button>
      )}

      {open && (
        <div style={{ position:'fixed', right:24, bottom:24, zIndex:9999, width:380, maxWidth:'94vw',
          height:560, maxHeight:'82vh', background:'#0d1016', border:'1px solid #1A1F2B',
          borderRadius:16, display:'flex', flexDirection:'column', overflow:'hidden',
          boxShadow:'0 20px 60px rgba(0,0,0,0.6)' }}>

          <div style={{ background:'linear-gradient(135deg,#1a1407,#0d1016)', padding:'14px 16px',
            display:'flex', alignItems:'center', justifyContent:'space-between', borderBottom:'1px solid #1A1F2B' }}>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ width:34, height:34, borderRadius:9, background:'rgba(232,184,75,0.16)',
                display:'flex', alignItems:'center', justifyContent:'center', fontSize:18 }}>🤖</div>
              <div>
                <div style={{ fontWeight:800, color:'#fff', fontSize:14 }}>TNFX Assistant</div>
                <div style={{ fontSize:10, color:GOLD }}>● Online · here to help</div>
              </div>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:6 }}>
              <button onClick={() => setAiNote(true)} title="Tell the assistant how to answer"
                style={{ background:'rgba(240,85,106,0.15)', border:'1px solid rgba(240,85,106,0.5)',
                  color:'#f0556a', fontSize:11, fontWeight:800, cursor:'pointer', borderRadius:8,
                  padding:'5px 9px', fontFamily:'inherit' }}>🎫 Note</button>
              <button onClick={() => setOpen(false)} style={{ background:'transparent', border:'none',
                color:'#8A93A3', fontSize:22, cursor:'pointer', lineHeight:1 }}>×</button>
            </div>
          </div>
          {aiNote && <TicketModal aiMode onClose={() => setAiNote(false)} />}

          <div style={{ flex:1, overflowY:'auto', padding:14, display:'flex', flexDirection:'column', gap:10 }}>
            {msgs.length === 0 && (
              <div style={{ color:'#9aa3b3', fontSize:13 }}>
                <div style={{ marginBottom:12, color:'#cfd6e2' }}>
                  👋 Hi! I'm your TNFX assistant. Ask me about your account, deposits & withdrawals,
                  your trades, the market, or our IB program.
                </div>
                <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
                  {suggest.map((s, i) => (
                    <button key={i} onClick={() => send(s)} style={{ background:'#161b24',
                      border:'1px solid #2a3240', color:'#cfd6e2', borderRadius:16, padding:'7px 12px',
                      fontSize:12, cursor:'pointer', fontFamily:'inherit' }}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth:'86%' }}>
                <div dir="auto" style={{ background: m.role === 'user' ? 'linear-gradient(135deg,#F8500A,#C77B45)' : '#161b24',
                  color: m.role === 'user' ? '#0B0E14' : '#E7ECF3',
                  padding:'10px 13px', borderRadius:13,
                  borderBottomRightRadius: m.role === 'user' ? 4 : 13,
                  borderBottomLeftRadius: m.role === 'user' ? 13 : 4,
                  fontSize:13.5, lineHeight:1.5, whiteSpace:'pre-wrap', wordBreak:'break-word', textAlign:'start' }}>
                  {m.image && (
                    <img src={m.image} alt="attachment" style={{ display:'block', maxWidth:'100%',
                      maxHeight:180, borderRadius:8, marginBottom: m.content ? 8 : 0 }} />
                  )}
                  {m.content}
                </div>
              </div>
            ))}
            {typing && (
              <div style={{ alignSelf:'flex-start', background:'#161b24', borderRadius:13,
                borderBottomLeftRadius:4, padding:'10px 14px', display:'flex', gap:4, alignItems:'center' }}>
                <span style={{ width:7, height:7, borderRadius:'50%', background:'#8A93A3', animation:'tnfxBlink 1s infinite' }} />
                <span style={{ width:7, height:7, borderRadius:'50%', background:'#8A93A3', animation:'tnfxBlink 1s infinite .2s' }} />
                <span style={{ width:7, height:7, borderRadius:'50%', background:'#8A93A3', animation:'tnfxBlink 1s infinite .4s' }} />
                <style>{`@keyframes tnfxBlink{0%,60%,100%{opacity:.25}30%{opacity:1}}`}</style>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div style={{ borderTop:'1px solid #1A1F2B', padding:10 }}>
            {imgData && (
              <div style={{ marginBottom:8, display:'flex', alignItems:'center', gap:8,
                background:'#161b24', border:'1px solid #2a3240', borderRadius:10, padding:6 }}>
                <img src={imgData} alt="to send" style={{ height:42, width:42, objectFit:'cover', borderRadius:6 }} />
                <span style={{ flex:1, color:'#9aa3b3', fontSize:12 }}>Image attached</span>
                <button onClick={clearImage} title="Remove image"
                  style={{ background:'transparent', border:'none', color:'#8A93A3', fontSize:18,
                    cursor:'pointer', lineHeight:1 }}>✕</button>
              </div>
            )}
            <div style={{ display:'flex', gap:8 }}>
              <input ref={fileRef} type="file" accept="image/*" onChange={onPickImage} style={{ display:'none' }} />
              <button onClick={() => fileRef.current?.click()} disabled={busy} title="Attach an image"
                style={{ background:'#161b24', border:'1px solid #2a3240', borderRadius:10, color:'#E7ECF3',
                  width:42, fontSize:18, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1,
                  fontFamily:'inherit' }}>📎</button>
              <textarea value={input} onChange={e => setInput(e.target.value)} dir="auto"
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Type your message…" rows={1}
                style={{ flex:1, resize:'none', background:'#161b24', border:'1px solid #2a3240',
                  borderRadius:10, color:'#E7ECF3', padding:'10px 12px', fontSize:13.5,
                  fontFamily:'inherit', outline:'none', maxHeight:90, textAlign:'start' }} />
              <button onClick={() => send()} disabled={busy || (!input.trim() && !imgData)}
                style={{ background:'linear-gradient(135deg,#F8500A,#C77B45)', border:'none', borderRadius:10,
                  color:'#0B0E14', fontWeight:800, padding:'0 16px', cursor: busy ? 'default' : 'pointer',
                  opacity: (busy || (!input.trim() && !imgData)) ? 0.5 : 1, fontFamily:'inherit' }}>➤</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
