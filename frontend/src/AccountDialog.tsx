import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, UserRound, X } from 'lucide-react';
import type { Profile } from './types';

export default function AccountDialog({username, profiles, onSave, onClose}: {
  username: string; profiles: Profile[]; onSave: (value: string) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [input, setInput] = useState(username);
  useEffect(() => {
    const element = dialog.current!;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    element.querySelector('input')?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { element.close(); document.body.style.overflow = previousOverflow; opener?.focus(); };
  }, []);

  return <dialog ref={dialog} className="account-dialog" aria-labelledby="account-title" aria-describedby="account-description"
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)'));
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}
    onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) {
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
    } }}>
    <div className="account-dialog-heading"><UserRound size={21} aria-hidden="true"/>
      <button className="icon-button" type="button" onClick={onClose} aria-label="Close account settings"><X size={20}/></button>
    </div>
    <h2 id="account-title">Your Chess.com account</h2>
    <p id="account-description">Add your username once. We’ll check for new games whenever you open or reload Chess study.</p>
    <form onSubmit={event => { event.preventDefault(); onSave(input.trim().toLowerCase()); onClose(); }}>
      <label htmlFor="account-username">Chess.com username</label>
      <input id="account-username" name="username" value={input} onChange={event => setInput(event.target.value)}
        autoComplete="off" autoCapitalize="none" spellCheck={false} required maxLength={50}
        pattern="[A-Za-z0-9_\-]+" title="Enter your Chess.com username using letters, numbers, underscores, or hyphens."
        placeholder="Enter your username" aria-describedby="account-hint"/>
      <p id="account-hint">Public games only. No password needed.</p>
      <button type="submit" className="primary-button" disabled={!input.trim()}>{username ? 'Save account' : 'Add account'}<ArrowRight size={16}/></button>
    </form>
    {profiles.some(profile => profile.username !== username) && <div className="saved-accounts">
      <h3>Saved accounts</h3>
      {profiles.map(profile => <button key={profile.username} type="button" onClick={() => { onSave(profile.username); onClose(); }}>
        <UserRound size={16}/><span>{profile.username}</span>{profile.username === username && <Check size={16} aria-label="Current account"/>}
      </button>)}
    </div>}
    <p className="account-footnote">Your first sync adds up to 50 recent completed games. New games are added automatically after that.</p>
  </dialog>;
}
