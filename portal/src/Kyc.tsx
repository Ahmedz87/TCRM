import React, { useState } from 'react';
import { apiPost } from './api';
import { TH } from './theme';
import { Wizard, OptionCard, primaryBtn } from './Wizard';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

// Slim banner shown at top when client is unverified.
// While documents are in review we show a LIVE, animated KPI (the AI is reading the docs);
// if nothing was uploaded yet (skipped) we show the red "verify now" prompt instead.
export function KycBanner({ status, reason, existingAccount, needFamilyId, poaHolder, idApproved, onStart, onLogin, onRefresh }:
  { status: string; reason?: string; existingAccount?: { email_masked?: string; phone_masked?: string };
    needFamilyId?: boolean; poaHolder?: string; idApproved?: boolean; onStart: () => void; onLogin?: () => void; onRefresh?: () => void }) {
  const inReview = status === 'pending_review' || status === 'in_review' || status === 'submitted';
  const rejected = status === 'rejected';
  const exists = status === 'exists';
  const docsNeeded = status === 'docs_needed';
  const [famOpen, setFamOpen] = React.useState(false);
  const [poaOpen, setPoaOpen] = React.useState(false);
  const [dots, setDots] = React.useState('');
  const [dismissed, setDismissed] = React.useState(() => { try { return localStorage.getItem('kyc_verified_dismissed') === '1'; } catch { return false; } });
  React.useEffect(() => {
    if (!inReview) return;
    const id = setInterval(() => setDots(d => (d.length >= 3 ? '' : d + '.')), 450);
    return () => clearInterval(id);
  }, [inReview]);
  // Verified -> a green confirmation bar the client can dismiss with the ✕.
  if (status === 'verified') {
    if (dismissed) return null;
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', marginBottom: 18, borderRadius: TH.radiusSm, background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.30)' }}>
        <span style={{ fontSize: 18 }}>✅</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#34D399' }}>Your identity is verified — Approved</div>
          <div style={{ fontSize: 11.5, color: TH.muted }}>Your account is fully verified. All features and withdrawals are unlocked.</div>
        </div>
        <button onClick={() => { try { localStorage.setItem('kyc_verified_dismissed', '1'); } catch {} setDismissed(true); }}
          title="Dismiss" style={{ background: 'none', border: 'none', color: TH.muted, fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: '0 4px' }}>✕</button>
      </div>
    );
  }

  // Documents still needed -> show TWO stacked KPIs:
  //   • TOP  : a GREEN "ID approved ✅" strip once the ID itself has passed (or an amber "reviewing
  //            your ID" strip during the brief AI check).
  //   • BELOW: a separate actionable card for whatever is still missing (proof of address, or — when
  //            the address proof is in an UNIDENTIFIED person's name — that person's ID).
  if (docsNeeded) {
    const TopKpi = idApproved ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', marginBottom: 12, borderRadius: TH.radiusSm, background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.30)' }}>
        <span style={{ fontSize: 18 }}>✅</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#34D399' }}>Your ID is approved</div>
          <div style={{ fontSize: 11.5, color: TH.muted }}>Identity confirmed. Just one more document below to finish.</div>
        </div>
      </div>
    ) : (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', marginBottom: 12, borderRadius: TH.radiusSm, background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.28)' }}>
        <span style={{ display: 'inline-block', width: 16, height: 16, borderRadius: 99, border: `2px solid ${TH.gold}`, borderTopColor: 'transparent', animation: 'tnfxspin 0.8s linear infinite' }} />
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: TH.gold }}>We're reviewing your ID…</div>
          <div style={{ fontSize: 11.5, color: TH.muted }}>This takes a few moments. Meanwhile, add the document below.</div>
        </div>
        <style>{'@keyframes tnfxspin{to{transform:rotate(360deg)}}'}</style>
      </div>
    );
    // BELOW card: the specific missing-document ask.
    const AskCard = needFamilyId ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', marginBottom: 18, borderRadius: TH.radiusSm, flexWrap: 'wrap', background: 'rgba(232,184,75,0.10)', border: '1px solid rgba(232,184,75,0.32)' }}>
        <span style={{ fontSize: 18 }}>👪</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: TH.gold }}>Your proof of address is in someone else's name</div>
          <div style={{ fontSize: 11.5, color: TH.muted, lineHeight: 1.5 }}>
            It's in the name of <b style={{ color: TH.text }}>{poaHolder || 'another person'}</b>. If this is your husband/wife, parent or a family member, upload THEIR ID — we confirm family by the Family ID on the back of the card.
          </div>
        </div>
        <button onClick={() => setFamOpen(true)} style={{ padding: '8px 16px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>Upload their ID</button>
      </div>
    ) : (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', marginBottom: 18, borderRadius: TH.radiusSm, flexWrap: 'wrap', background: 'rgba(232,184,75,0.10)', border: '1px solid rgba(232,184,75,0.32)' }}>
        <span style={{ fontSize: 18 }}>📄</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: TH.gold }}>Proof of address needed</div>
          <div style={{ fontSize: 11.5, color: TH.muted }}>Please upload a recent proof of address (utility bill / bank statement) to finish verifying your account.</div>
        </div>
        <button onClick={() => setPoaOpen(true)} style={{ padding: '8px 16px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>Upload</button>
      </div>
    );
    return (
      <>
        {TopKpi}
        {AskCard}
        {famOpen && <FamilyIdUpload holder={poaHolder} onClose={() => setFamOpen(false)} onDone={() => { setFamOpen(false); onRefresh && onRefresh(); }} />}
        {poaOpen && <PoaUpload onClose={() => setPoaOpen(false)} onDone={() => { setPoaOpen(false); onRefresh && onRefresh(); }} />}
      </>
    );
  }

  // "You already have an account" — the ID matched an existing account: tell them to log in,
  // and show their existing email/phone MASKED so they recognise it without us leaking it.
  if (exists) {
    const em = existingAccount?.email_masked, ph = existingAccount?.phone_masked;
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', marginBottom: 18, borderRadius: TH.radiusSm, flexWrap: 'wrap', background: 'rgba(58,134,255,0.08)', border: '1px solid rgba(58,134,255,0.30)' }}>
        <span style={{ fontSize: 18 }}>👤</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#3a86ff' }}>You already have an account with us</div>
          <div style={{ fontSize: 11.5, color: TH.muted, lineHeight: 1.5 }}>
            {reason || 'This ID is already registered. Please log in to your existing account instead of creating a new one.'}
            {(em || ph) && <> <br />Registered to: {em ? <b style={{ color: TH.text }}>{em}</b> : null}{em && ph ? ' · ' : ''}{ph ? <b style={{ color: TH.text }}>{ph}</b> : null}</>}
          </div>
        </div>
        {onLogin && <button onClick={onLogin} style={{ padding: '8px 16px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>Log in</button>}
      </div>
    );
  }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', marginBottom: 18,
      borderRadius: TH.radiusSm, flexWrap: 'wrap',
      background: inReview ? 'rgba(232,184,75,0.08)' : 'rgba(240,85,106,0.08)',
      border: `1px solid ${inReview ? 'rgba(232,184,75,0.28)' : 'rgba(240,85,106,0.28)'}`,
    }}>
      {inReview
        ? <span style={{ display: 'inline-block', width: 16, height: 16, borderRadius: 99, border: `2px solid ${TH.gold}`, borderTopColor: 'transparent', animation: 'tnfxspin 0.8s linear infinite' }} />
        : <span style={{ fontSize: 18 }}>{rejected ? '⚠️' : '🪪'}</span>}
      <div style={{ flex: 1, minWidth: 180 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: inReview ? TH.gold : TH.neg }}>
          {inReview ? <>Your KYC is under review<span style={{ display: 'inline-block', width: 16, textAlign: 'left' }}>{dots}</span></>
            : rejected ? 'Verification needs attention' : 'Verify your identity'}
        </div>
        <div style={{ fontSize: 11.5, color: TH.muted }}>
          {inReview ? 'Our verification team is reviewing your documents — this usually takes a few minutes.'
            : rejected ? (reason || "We couldn't verify your documents — please review and upload again.")
            : 'Complete KYC to unlock withdrawals and full account features.'}
        </div>
      </div>
      {!inReview && <button onClick={onStart} style={{ padding: '8px 16px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{rejected ? 'Upload again' : 'Verify now'}</button>}
      {inReview && <style>{'@keyframes tnfxspin{to{transform:rotate(360deg)}}'}</style>}
    </div>
  );
}

const STEPS = ['Document type', 'Upload', 'Done'];

// Read a File as a base64 string (no data: prefix). Returns '' on failure.
function fileToB64(file: File): Promise<string> {
  return new Promise((resolve) => {
    try {
      const r = new FileReader();
      r.onload = () => {
        const s = String(r.result || '');
        const comma = s.indexOf(',');
        resolve(comma >= 0 ? s.slice(comma + 1) : s);
      };
      r.onerror = () => resolve('');
      r.readAsDataURL(file);
    } catch { resolve(''); }
  });
}

const MAX_UPLOAD_BYTES = 7 * 1024 * 1024; // keep in sync with backend kyc_ai.MAX_IMAGE_BYTES

export function KycWizard({ onClose, onDone }: { onClose: () => void; onDone?: () => void }) {
  const mobile = useIsMobile();
  const [step, setStep] = useState(0);
  const [docType, setDocType] = useState('national_id');
  const [frontName, setFrontName] = useState('');
  const [backName, setBackName] = useState('');
  const [poaName, setPoaName] = useState('');   // proof of address (ticket #7)
  const [frontFile, setFrontFile] = useState<File | null>(null);  // actual image bytes for OCR
  const [backFile, setBackFile] = useState<File | null>(null);
  const [poaFile, setPoaFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [ocrNote, setOcrNote] = useState('');

  // Upload the document AND submit for review in one step — our AI reads the ID server-side; we no
  // longer make the client review/confirm the extracted fields.
  const scanAndSubmit = async () => {
    setBusy(true); setOcrNote('');
    try {
      const tooBig = [frontFile, backFile, poaFile].some(f => f && f.size > MAX_UPLOAD_BYTES);
      if (tooBig) { setOcrNote('One image is over 7MB — please upload smaller/compressed photos and try again.'); setBusy(false); return; }
      const image = frontFile ? (await fileToB64(frontFile)) || undefined : undefined;
      const image_back = backFile ? (await fileToB64(backFile)) || undefined : undefined;
      const image_poa = poaFile ? (await fileToB64(poaFile)) || undefined : undefined;
      const res: any = await apiPost('/portal/kyc/upload', { doc_type: docType, image, image_back, image_poa });
      const extracted = res?.extracted || {};
      await apiPost('/portal/kyc/submit', { document_type: docType, fields: extracted });
      setStep(2); onDone && onDone();
    } catch (e) { /* ignore */ }
    finally { setBusy(false); }
  };

  return (
    <div style={{ padding: '8px 0' }}>
      <Wizard
        steps={STEPS} current={step}
        onBack={step === 0 ? onClose : step === 1 ? () => setStep(0) : undefined}
        onNext={
          step === 0 ? () => setStep(1) :
          step === 1 ? (frontName ? scanAndSubmit : undefined) : undefined
        }
        nextLabel={step === 1 ? (busy ? 'Submitting…' : 'Submit for review') : 'Continue'}
        nextDisabled={(step === 1 && !frontName) || busy}
        hideNav={step === 2}
      >
        {step === 0 && (
          <>
            <OptionCard active={docType === 'national_id'} onClick={() => setDocType('national_id')} icon="🪪" title="National ID" sub="Front & back of your ID card" />
            <OptionCard active={docType === 'passport'} onClick={() => setDocType('passport')} icon="📕" title="Passport" sub="Photo page" />
            <OptionCard active={docType === 'drivers_license'} onClick={() => setDocType('drivers_license')} icon="🚗" title="Driver's license" sub="Front & back" />
          </>
        )}

        {step === 1 && (
          <>
            <UploadBox label={docType === 'passport' ? 'Passport photo page' : 'Front side'} name={frontName} onPick={(n, f) => { setFrontName(n); setFrontFile(f || null); }} />
            {docType !== 'passport' && <UploadBox label="Back side" name={backName} onPick={(n, f) => { setBackName(n); setBackFile(f || null); }} />}
            <div style={{ fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, margin: '14px 0 6px' }}>Proof of address</div>
            <UploadBox label="Proof of address (utility bill / bank statement)" name={poaName} onPick={(n, f) => { setPoaName(n); setPoaFile(f || null); }} />
            <div style={{ fontSize: 11.5, color: TH.muted, marginTop: 8, lineHeight: 1.5 }}>
              Make sure the document is well-lit, all corners visible, and text is readable. You can upload an image or take a photo with your camera. We'll automatically read the details for you.
            </div>

            {/* Scan to continue on your phone (ticket #7) */}
            <div style={{ marginTop: 16, padding: 14, borderRadius: TH.radius, background: TH.panel, border: `1px solid ${TH.border2}`, display: 'flex', gap: 14, alignItems: 'center', flexDirection: mobile ? 'column' : 'row', textAlign: mobile ? 'center' : 'left' }}>
              <img alt="Scan to upload on mobile" width={104} height={104} style={{ borderRadius: 8, background: '#fff', padding: 4, flexShrink: 0, maxWidth: '100%' }}
                src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(window.location.origin + '/portal/')}`} />
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: TH.text }}>📱 Prefer your phone's camera?</div>
                <div style={{ fontSize: 12, color: TH.muted, marginTop: 4, lineHeight: 1.5 }}>
                  Scan this code with your phone to open the portal on mobile, then sign in and finish uploading / taking photos of your documents here.
                </div>
              </div>
            </div>
          </>
        )}

        {step === 1 && ocrNote && (
          <div style={{ background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.28)', borderRadius: TH.radiusSm, padding: '10px 14px', fontSize: 12, color: TH.gold, marginTop: 12 }}>
            ⚠ {ocrNote}
          </div>
        )}

        {step === 2 && (
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: 60, height: 60, borderRadius: 99, background: 'rgba(58,210,159,0.14)', display: 'grid', placeItems: 'center', margin: '0 auto 16px', fontSize: 28 }}>✓</div>
            <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 6 }}>Submitted for review</div>
            <div style={{ fontSize: 13, color: TH.muted, marginBottom: 22, lineHeight: 1.5 }}>Your documents are with our verification team. You'll be notified once your account is verified — usually within a few minutes.</div>
            <button onClick={onClose} style={{ ...primaryBtn, width: '100%' }}>Back to portal</button>
          </div>
        )}
      </Wizard>
    </div>
  );
}

function UploadBox({ label, name, onPick }: { label: string; name: string; onPick: (n: string, f?: File) => void }) {
  const btn: any = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: TH.radiusSm, background: TH.panel2, border: `1px solid ${TH.border2}`, color: TH.text, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' };
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    onPick(f?.name || '', f || undefined);
  };
  return (
    <div style={{ border: `1.5px dashed ${name ? TH.accent : TH.border2}`, borderRadius: TH.radius, padding: 18, textAlign: 'center', background: TH.panel, marginBottom: 10 }}>
      <div style={{ fontSize: 24, marginBottom: 6 }}>{name ? '✓' : '📄'}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: name ? TH.accent : TH.text, marginBottom: 10 }}>{name || label}</div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
        <label style={btn}>📤 Upload
          <input type="file" accept="image/*" style={{ display: 'none' }} onChange={pick} />
        </label>
        <label style={btn}>📷 Take photo
          <input type="file" accept="image/*" capture={'environment' as any} style={{ display: 'none' }} onChange={pick} />
        </label>
      </div>
    </div>
  );
}

// Modal: upload the front + back of the family member's (husband/wife/parent) ID so we can confirm
// the household by matching the Family ID printed on the back against the client's own ID.
function FamilyIdUpload({ holder, onClose, onDone }: { holder?: string; onClose: () => void; onDone: () => void }) {
  const [front, setFront] = useState<File | undefined>();
  const [back, setBack] = useState<File | undefined>();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    if (!front && !back) { setErr("Please attach the family member's ID (front and back)."); return; }
    setBusy(true); setErr('');
    try {
      const image_family_id_front = front ? (await fileToB64(front)) || undefined : undefined;
      const image_family_id_back = back ? (await fileToB64(back)) || undefined : undefined;
      const res: any = await apiPost('/portal/kyc/family-id', { image_family_id_front, image_family_id_back });
      if (res && res.ok === false) { setErr(res.error || 'Upload failed.'); setBusy(false); return; }
      onDone();
    } catch (e: any) { setErr('Upload failed. Please try again.'); setBusy(false); }
  };
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 'min(440px,94vw)', background: TH.panel, border: `1px solid ${TH.border2}`, borderRadius: TH.radius, padding: 20 }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: TH.text, marginBottom: 4 }}>Family member's ID</div>
        <div style={{ fontSize: 12, color: TH.muted, lineHeight: 1.55, marginBottom: 14 }}>
          Your proof of address is in the name of <b style={{ color: TH.text }}>{holder || 'a family member'}</b>.
          Upload the front and back of their national ID — we confirm you're the same household by matching
          the <b style={{ color: TH.text }}>Family ID</b> on the back of the card. Our team will also review.
        </div>
        <UploadBox label="Family member ID — front" name={front?.name || ''} onPick={(_, f) => setFront(f)} />
        <UploadBox label="Family member ID — back (Family ID side)" name={back?.name || ''} onPick={(_, f) => setBack(f)} />
        {err && <div style={{ fontSize: 12, color: TH.neg, marginTop: 6 }}>{err}</div>}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
          <button onClick={onClose} disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, background: 'transparent', color: TH.muted, border: `1px solid ${TH.border2}`, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>Cancel</button>
          <button onClick={submit} disabled={busy} style={{ padding: '9px 18px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.7 : 1 }}>{busy ? 'Uploading…' : 'Submit'}</button>
        </div>
      </div>
    </div>
  );
}

// Focused modal to add JUST the proof of address (when the ID is already approved). Avoids re-running
// the whole registration wizard — uploads the bill and re-runs verification.
function PoaUpload({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | undefined>();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    if (!file) { setErr('Please attach your proof of address.'); return; }
    setBusy(true); setErr('');
    try {
      const image_poa = (await fileToB64(file)) || undefined;
      if (!image_poa) { setErr("Couldn't read that file — try another photo."); setBusy(false); return; }
      const res: any = await apiPost('/portal/kyc/upload', { doc_type: 'national_id', image_poa });
      if (res && res.ok === false) { setErr(res.error || 'Upload failed.'); setBusy(false); return; }
      await apiPost('/portal/kyc/submit', { document_type: 'national_id', fields: {} });
      onDone();
    } catch (e: any) { setErr('Upload failed. Please try again.'); setBusy(false); }
  };
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 'min(440px,94vw)', background: TH.panel, border: `1px solid ${TH.border2}`, borderRadius: TH.radius, padding: 20 }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: TH.text, marginBottom: 4 }}>Upload your proof of address</div>
        <div style={{ fontSize: 12, color: TH.muted, lineHeight: 1.55, marginBottom: 14 }}>
          A recent utility bill, bank statement, tenancy contract or residence card showing your address.
          If it's in a family member's name (parent, spouse, sibling), that's accepted — we'll recognise it.
        </div>
        <UploadBox label="Proof of address" name={file?.name || ''} onPick={(_, f) => setFile(f)} />
        {err && <div style={{ fontSize: 12, color: TH.neg, marginTop: 6 }}>{err}</div>}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
          <button onClick={onClose} disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, background: 'transparent', color: TH.muted, border: `1px solid ${TH.border2}`, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>Cancel</button>
          <button onClick={submit} disabled={busy} style={{ padding: '9px 18px', borderRadius: 8, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.7 : 1 }}>{busy ? 'Uploading…' : 'Submit'}</button>
        </div>
      </div>
    </div>
  );
}
