import React, { useState } from 'react';
import { placeCall, dialNumber } from './api';

// ── Yeastar helper ─────────────────────────────────────────────────────────
// Routes through the backend Yeastar proxy (placeCall in api.ts); auto-falls back to tel:.
const yeastarCall = placeCall;

// ══════════════════════════════════════════════════════════════════════════
// PHONE MODAL — shared between Leads + Clients + Trading Accounts
// ══════════════════════════════════════════════════════════════════════════
export function PhoneModal({ contact, onClose }: {
  contact: { name: string; phone: string };
  onClose: () => void;
}) {
  const [calling, setCalling] = useState(false);
  const [called,  setCalled]  = useState(false);
  const [result,  setResult]  = useState<any>(null);
  const phone       = contact.phone || '';
  const whatsappNum = phone.replace(/[^0-9]/g,'');
  const agentName   = localStorage.getItem('userName') || 'TNFX Team';

  const handleCall = async () => {
    setCalling(true);
    const r = await yeastarCall(phone);
    setCalling(false);
    setCalled(true);
    setResult(r);
    if (r?.ok) setTimeout(onClose, 3000);  // keep open on failure so the error is readable
  };
  const ok = result?.ok;
  const callLabel = called ? (ok ? `Ringing ext ${result?.caller}…` : 'Call failed')
                    : calling ? 'Connecting…' : 'Call via Yeastar PBX';
  const callSub = called
    ? (ok ? `Pick up ext ${result?.caller}, then it dials ${phone}`
          : (result?.errmsg || 'PBX did not accept the call'))
    : 'Rings your extension first, then dials';

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.75)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:24, width:320 }} onClick={e=>e.stopPropagation()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
          <div style={{ fontSize:14, fontWeight:500 }}>Contact {contact.name}</div>
          <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:18 }}>✕</div>
        </div>

        {/* Avatar + number */}
        <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 14px', background:'#373f4d', borderRadius:10, marginBottom:16 }}>
          <div style={{ width:36, height:36, borderRadius:10, background:'linear-gradient(135deg,#0066ff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:15, color:'#fff' }}>
            {contact.name?.[0]?.toUpperCase() || '?'}
          </div>
          <div>
            <div style={{ fontSize:13, fontWeight:500 }}>{contact.name}</div>
            <div style={{ fontSize:12, color:'#888', fontFamily:'monospace' }}>{phone || 'No phone'}</div>
          </div>
        </div>

        {!phone ? (
          <div style={{ textAlign:'center', color:'#555', fontSize:13, padding:'20px 0' }}>No phone number on record</div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            <button onClick={handleCall} disabled={calling || (called && ok)}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px',
                background: called && !ok ? 'rgba(255,77,77,0.08)' : 'rgba(0,229,160,0.08)',
                border:`1px solid ${called ? (ok?'#00e5a0':'#ff4d4d') : 'rgba(0,229,160,0.3)'}`,
                borderRadius:10, color: called && !ok ? '#ff4d4d' : '#00e5a0', cursor:(called&&ok)?'default':'pointer' }}>
              <div style={{ width:40, height:40, borderRadius:10, background: called && !ok ? 'rgba(255,77,77,0.15)' : 'rgba(0,229,160,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>
                {called ? (ok?'✓':'✕') : calling?'⟳':'📞'}
              </div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>{callLabel}</div>
                <div style={{ fontSize:11, color:'#888', marginTop:2 }}>{callSub}</div>
              </div>
            </button>

            <button onClick={()=>{ window.open(`https://wa.me/${whatsappNum}?text=Hello ${contact.name}, this is ${agentName} from TNFX. How can I assist you today?`,'_blank'); onClose(); }}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px', background:'rgba(37,211,102,0.08)', border:'1px solid rgba(37,211,102,0.3)', borderRadius:10, color:'#25d366', cursor:'pointer' }}>
              <div style={{ width:40, height:40, borderRadius:10, background:'rgba(37,211,102,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>💬</div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>Open WhatsApp</div>
                <div style={{ fontSize:11, color:'#555', marginTop:2 }}>Opens chat with greeting pre-filled</div>
              </div>
            </button>

            <button onClick={()=>{ window.location.href=`tel:${dialNumber(phone)}`; onClose(); }}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px', background:'rgba(0,102,255,0.08)', border:'1px solid rgba(0,102,255,0.3)', borderRadius:10, color:'#4d9fff', cursor:'pointer' }}>
              <div style={{ width:40, height:40, borderRadius:10, background:'rgba(0,102,255,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>📱</div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>Regular call (device)</div>
                <div style={{ fontSize:11, color:'#555', marginTop:2 }}>Uses your phone or PC dialer</div>
              </div>
            </button>
          </div>
        )}
        <div style={{ marginTop:14, padding:'8px 12px', background:'#373f4d', borderRadius:8, fontSize:11, color:'#555' }}>
          💡 Yeastar PBX connected. Set your agent extension in Settings (defaults to ext 101).
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════
// EMAIL TEMPLATES
// ══════════════════════════════════════════════════════════════════════════
const LEAD_TEMPLATES = [
  {
    id: 'lead_welcome',
    label: '👋 Welcome — First contact',
    subject: 'Welcome to TNFX — Start Trading Today',
    body: (name: string) => `Dear ${name},

Thank you for your interest in TNFX. We are a regulated forex and CFD broker offering competitive spreads, advanced trading platforms, and dedicated support.

To get started, simply register your account at our website and our team will guide you through the process.

We look forward to welcoming you to the TNFX family.

Best regards,
TNFX Team`,
  },
  {
    id: 'lead_followup',
    label: '🔄 Follow-up — No response',
    subject: 'Following up on your trading inquiry — TNFX',
    body: (name: string) => `Dear ${name},

We wanted to follow up on your recent inquiry about trading with TNFX.

We understand you may have been busy, but we don't want you to miss out on our current promotions and market opportunities.

Our team is available to answer any questions and help you get started. Please feel free to reach out at your convenience.

Best regards,
TNFX Team`,
  },
  {
    id: 'lead_promotion',
    label: '🎁 Welcome Bonus offer',
    subject: 'Exclusive Welcome Bonus — TNFX',
    body: (name: string) => `Dear ${name},

We have an exclusive offer just for you!

Open and verify your account today and receive a $50 Welcome Bonus — no deposit required.

✅ Regulated broker
✅ Tight spreads on Gold, Forex & Indices
✅ MT5 platform
✅ 24/5 dedicated support

Don't miss this limited-time offer. Register now and claim your bonus.

Best regards,
TNFX Team`,
  },
  {
    id: 'lead_kyc_reminder',
    label: '🪪 Complete your verification',
    subject: 'Complete your KYC verification — TNFX',
    body: (name: string) => `Dear ${name},

Your TNFX account is almost ready! To activate your account and start trading, please complete your identity verification.

You will need:
1. A valid government-issued ID (passport or national ID)
2. Proof of address (utility bill or bank statement)

Upload your documents through your client portal. Verification is usually completed within 24 hours.

Best regards,
TNFX Compliance Team`,
  },
  {
    id: 'lead_callback',
    label: '📅 Callback confirmation',
    subject: 'Your callback is scheduled — TNFX',
    body: (name: string) => `Dear ${name},

This is a confirmation that our team will contact you as scheduled.

Our trading specialist will be happy to:
• Walk you through our trading platforms
• Answer your questions about trading conditions
• Help you set up your account

If you need to reschedule, please don't hesitate to reach out.

Best regards,
TNFX Team`,
  },
];

const CLIENT_TEMPLATES = [
  {
    id: 'client_deposit',
    label: '💰 Make a deposit',
    subject: 'Fund your trading account — TNFX',
    body: (name: string) => `Dear ${name},

We noticed your trading account balance is running low. Don't miss out on market opportunities!

Fund your account today and take advantage of:
✅ Instant deposits via bank transfer, card or e-wallet
✅ No deposit fees
✅ Access to all trading instruments immediately

Log in to your client portal to make a deposit.

Best regards,
TNFX Team`,
  },
  {
    id: 'client_deposit_bonus',
    label: '🎁 Deposit Bonus offer',
    subject: 'Special Deposit Bonus — exclusive for you — TNFX',
    body: (name: string) => `Dear ${name},

As a valued TNFX client, we have a special offer for you!

Make a deposit this week and receive up to 50% bonus on your deposit.

This is a limited-time offer exclusively for existing clients. Log in to your portal to claim your bonus before it expires.

Best regards,
TNFX Team`,
  },
  {
    id: 'client_kyc_update',
    label: '🪪 KYC documents expiring',
    subject: 'Important: Your KYC documents need renewal — TNFX',
    body: (name: string) => `Dear ${name},

Our records show that your identity verification documents are due for renewal.

To continue trading without interruption, please upload updated documents:
• Valid government-issued ID
• Recent proof of address (issued within 3 months)

Please log in to your client portal and upload your documents within the next 14 days to avoid any disruption to your account.

Best regards,
TNFX Compliance Team`,
  },
  {
    id: 'client_reactivate',
    label: '🔄 Reactivation — inactive account',
    subject: 'We miss you! Your trading account is waiting — TNFX',
    body: (name: string) => `Dear ${name},

We noticed you haven't traded recently and wanted to check in.

The markets are full of opportunities right now, especially in Gold and major forex pairs. Our trading specialists are ready to help you get back on track.

Log in today and see what you have been missing.

Best regards,
TNFX Team`,
  },
  {
    id: 'client_withdrawal',
    label: '📤 Withdrawal processed',
    subject: 'Your withdrawal has been processed — TNFX',
    body: (name: string) => `Dear ${name},

Your withdrawal request has been processed and is on its way to your account.

Please allow 1-3 business days for the funds to appear depending on your payment method.

If you have any questions, our support team is available 24/5.

Best regards,
TNFX Finance Team`,
  },
  {
    id: 'client_welcome_back',
    label: '👋 Welcome back after deposit',
    subject: 'Welcome back to TNFX — your account is funded',
    body: (name: string) => `Dear ${name},

Great news! Your deposit has been received and your trading account is now funded.

You can now access:
✅ Full range of trading instruments
✅ Advanced charting tools
✅ Dedicated account manager

Log in to MT5 and start trading.

Best regards,
TNFX Team`,
  },
  {
    id: 'client_monthly_statement',
    label: '📊 Monthly account summary',
    subject: 'Your monthly trading summary — TNFX',
    body: (name: string) => `Dear ${name},

Here is a summary of your trading activity for this month.

Please log in to your client portal to view your full statement including:
• All trades placed
• Profit and loss summary
• Deposit and withdrawal history

If you have questions about your account performance, your dedicated account manager is here to help.

Best regards,
TNFX Team`,
  },
  {
    id: 'client_kyc_approved',
    label: '✅ KYC approved',
    subject: 'Your account is fully verified — TNFX',
    body: (name: string) => `Dear ${name},

Congratulations! Your identity verification has been completed successfully.

Your account is now fully verified and you have access to all features including:
✅ Full withdrawal rights
✅ Higher deposit limits
✅ Premium trading conditions

Thank you for completing your verification. Happy trading!

Best regards,
TNFX Compliance Team`,
  },
];


// ══════════════════════════════════════════════════════════════════════════
// EMAIL MODAL — shared between Leads + Clients + Trading Accounts
// ══════════════════════════════════════════════════════════════════════════
export function EmailModal({ contact, type='client', onClose }: {
  contact: { name: string; email: string };
  type?: 'lead' | 'client';
  onClose: () => void;
}) {
  const templates = type === 'lead' ? LEAD_TEMPLATES : CLIENT_TEMPLATES;
  const [selected, setSelected] = useState<any>(templates[0]);
  const [subject,  setSubject]  = useState(templates[0].subject);
  const [body,     setBody]     = useState(templates[0].body(contact.name));
  const [sending,  setSending]  = useState(false);
  const [sent,     setSent]     = useState(false);

  const selectTemplate = (t: any) => {
    setSelected(t);
    setSubject(t.subject);
    setBody(t.body(contact.name));
  };

  const sendEmail = () => {
    // Open default email client with prefilled content
    const mailto = `mailto:${contact.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.open(mailto, '_blank');
    setSent(true);
    setTimeout(onClose, 1500);
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.75)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:0, width:680, maxHeight:'85vh', display:'flex', flexDirection:'column', overflow:'hidden' }} onClick={e=>e.stopPropagation()}>

        {/* Header */}
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'16px 20px', borderBottom:'1px solid #4f596b' }}>
          <div>
            <div style={{ fontSize:14, fontWeight:500 }}>Email {contact.name}</div>
            <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{contact.email || 'No email address'}</div>
          </div>
          <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:18 }}>✕</div>
        </div>

        {!contact.email ? (
          <div style={{ padding:30, textAlign:'center', color:'#555' }}>No email address on record</div>
        ) : (
          <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
            {/* Template list */}
            <div style={{ width:220, borderRight:'1px solid #4f596b', overflowY:'auto', padding:8 }}>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, padding:'4px 8px', marginBottom:4 }}>
                {type === 'lead' ? 'Lead templates' : 'Client templates'}
              </div>
              {templates.map(t => (
                <div key={t.id} onClick={()=>selectTemplate(t)}
                  style={{ padding:'8px 10px', borderRadius:7, cursor:'pointer', fontSize:11, marginBottom:2, background:selected?.id===t.id?'rgba(0,229,160,0.08)':'transparent', border:`1px solid ${selected?.id===t.id?'rgba(0,229,160,0.3)':'transparent'}`, color:selected?.id===t.id?'#00e5a0':'#888' }}
                  onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')}
                  onMouseLeave={e=>(e.currentTarget.style.background=selected?.id===t.id?'rgba(0,229,160,0.08)':'transparent')}>
                  {t.label}
                </div>
              ))}
            </div>

            {/* Email editor */}
            <div style={{ flex:1, display:'flex', flexDirection:'column', padding:16, overflow:'hidden' }}>
              <div style={{ marginBottom:10 }}>
                <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Subject</div>
                <input value={subject} onChange={e=>setSubject(e.target.value)}
                  style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
              </div>
              <div style={{ flex:1, display:'flex', flexDirection:'column', minHeight:0 }}>
                <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Message</div>
                <textarea value={body} onChange={e=>setBody(e.target.value)}
                  style={{ flex:1, padding:'10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:12, outline:'none', resize:'none' as any, fontFamily:'inherit', minHeight:200 }} />
              </div>
              <div style={{ display:'flex', justifyContent:'flex-end', gap:8, marginTop:12 }}>
                <button onClick={onClose}
                  style={{ padding:'8px 16px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#888', cursor:'pointer', fontSize:13 }}>
                  Cancel
                </button>
                <button onClick={sendEmail} disabled={sending || sent}
                  style={{ padding:'8px 20px', background:sent?'rgba(0,229,160,0.2)':'#00e5a0', border:'none', borderRadius:7, color:sent?'#00e5a0':'#000', fontWeight:700, cursor:'pointer', fontSize:13 }}>
                  {sent ? '✓ Opening email client...' : '✉️ Send Email'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
