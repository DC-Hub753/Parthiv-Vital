import { useState } from 'react';
import { CheckCheck, Undo2, BellRing, Siren, Info, CheckCircle2, Stethoscope, CheckSquare, UserCheck, AlertTriangle, Trash2, History, ChevronDown } from 'lucide-react';
import { formatTimeAgo } from '../../utils/format.ts';
import type { AlertItem, AlertSeverity } from '../../types/index.ts';
import { api } from '../../services/api.ts';

const SEV = {
  critical: { cls: 'text-white border-transparent', style: { background: 'linear-gradient(135deg,#e11d48,#f43f5e)' }, Icon: Siren },
  high: { cls: 'text-white border-transparent', style: { background: 'linear-gradient(135deg,#ea580c,#f97316)' }, Icon: BellRing },
  moderate: { cls: 'bg-amber-100 text-amber-800 border border-amber-200', style: undefined, Icon: BellRing },
  info: { cls: 'bg-cyan-50 text-cyan-800 border border-cyan-200 dark:bg-cyan-950/50 dark:text-cyan-200 dark:border-cyan-900/60', style: undefined, Icon: Info },
} as const;

export function AlertCard({
  a,
  onAck,
  onResolve,
  onReopen,
  onDelete,
}: {
  a: AlertItem;
  onAck: () => void;
  onResolve?: () => void;
  onReopen: () => void;
  onDelete?: () => void;
}) {
  const [showAudit, setShowAudit] = useState(false);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  const toggleAudit = async () => {
    if (showAudit) {
      setShowAudit(false);
      return;
    }
    setShowAudit(true);
    if (auditEvents.length === 0) {
      setLoadingAudit(true);
      try {
        const res = await api.getAlertAudit(a.id);
        setAuditEvents(res.items || []);
      } catch {
        // fallback empty
      } finally {
        setLoadingAudit(false);
      }
    }
  };
  const sev: AlertSeverity = a.severity;
  const entry = SEV[sev] ?? SEV.info;
  const { cls, Icon } = entry;

  return (
    <article className="card card-hover p-5 relative overflow-hidden">
      <span
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{
          background:
            sev === 'critical'
              ? '#e11d48'
              : sev === 'high'
              ? '#ea580c'
              : sev === 'moderate'
              ? '#d97706'
              : '#0891b2',
        }}
        aria-hidden
      />
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 text-[11px] font-extrabold px-2.5 py-1 rounded-full uppercase tracking-wide ${cls}`}
          style={entry.style}
        >
          <Icon size={13} aria-hidden /> {a.severity}
        </span>
        <span className="font-display font-extrabold">{a.patientId}</span>
        <span className="text-[11px] text-slate-400 tabular-nums">{formatTimeAgo(a.createdAt)}</span>

        {a.isOverdue && a.status !== 'resolved' && (
          <span className="inline-flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300">
            <AlertTriangle size={11} /> Overdue review
          </span>
        )}

        {a.assignedTo && (
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
            <UserCheck size={11} /> {a.assignedTo}
          </span>
        )}

        <span className="ml-auto inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-slate-400">
          {a.status === 'acknowledged' ? <CheckCircle2 size={13} className="text-teal-500" aria-hidden /> : null}
          <span className="capitalize">{a.status}</span>
        </span>
      </div>

      <h3 className="font-display font-bold mt-2.5 text-[16px] tracking-tight">{a.title}</h3>

      <div className="mt-3 rounded-2xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200/50 dark:border-white/[0.06] px-4 py-3 flex items-center gap-4">
        <div>
          <p className="eyebrow !text-[10px]">Risk change</p>
          <p className="metric text-lg tabular-nums">{a.riskBefore ?? '—'} → {a.riskAfter ?? '—'}</p>
        </div>
        <div className="h-8 w-px bg-slate-200 dark:bg-white/10" aria-hidden />
        <div>
          <p className="eyebrow !text-[10px]">Status</p>
          <p className="text-sm font-bold capitalize">{a.status}</p>
        </div>
        <div className="ml-auto hidden sm:flex items-center gap-1.5 text-[11px] font-bold text-teal-700 dark:text-teal-300">
          <Stethoscope size={13} aria-hidden />Review recommended
        </div>
      </div>

      <p className="text-sm text-slate-600 dark:text-slate-300 mt-3 leading-relaxed">{a.description}</p>

      {a.contributors && a.contributors.length > 0 && (
        <>
          <p className="eyebrow !text-[10px] mt-3">Observed contributors</p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {a.contributors.map((c: string) => (
              <li key={c} className="px-2 py-1 rounded-lg bg-slate-900/[0.04] dark:bg-white/[0.06] text-[11px] font-semibold">
                {c}
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {a.status === 'open' && (
          <button onClick={onAck} className="btn-primary !py-2">
            <CheckCheck size={15} aria-hidden /> Acknowledge
          </button>
        )}
        {a.status !== 'resolved' && onResolve && (
          <button onClick={onResolve} className="btn-secondary !py-2">
            <CheckSquare size={15} aria-hidden /> Resolve
          </button>
        )}
        {a.status === 'resolved' && (
          <button onClick={onReopen} className="btn-secondary !py-2">
            <Undo2 size={15} aria-hidden /> Reopen
          </button>
        )}
        <button
          onClick={() => void toggleAudit()}
          className="btn-secondary !py-2 text-slate-700 dark:text-slate-200"
          title="Inspect immutable audit record trail"
          aria-expanded={showAudit}
        >
          <History size={14} aria-hidden /> Audit Trail <ChevronDown size={14} className={showAudit ? 'rotate-180' : ''} aria-hidden />
        </button>
        {onDelete && (
          <button
            onClick={() => {
              if (window.confirm(`Permanently delete Alert #${a.id}? This action cannot be undone.`)) {
                onDelete();
              }
            }}
            className="btn-secondary !py-2 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30"
            title="Permanently remove alert"
          >
            <Trash2 size={14} aria-hidden /> Delete
          </button>
        )}
      </div>

      {showAudit && (
        <div className="mt-3 rounded-2xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200/50 dark:border-white/[0.06] p-3 text-xs">
          <div className="flex items-center gap-1.5 font-bold mb-2 text-slate-700 dark:text-slate-300">
            <History size={13} /> Alert Audit Trail
          </div>
          {loadingAudit ? (
            <p className="text-slate-400">Loading audit records…</p>
          ) : auditEvents.length === 0 ? (
            <p className="text-slate-400">No recorded audit history found.</p>
          ) : (
            <ol className="space-y-1.5">
              {auditEvents.map((ev) => (
                <li key={ev.id} className="border-l-2 border-teal-500 pl-2.5 py-0.5">
                  <div className="flex flex-wrap items-center justify-between gap-1">
                    <span className="font-semibold capitalize text-slate-800 dark:text-slate-200">
                      {ev.action?.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {new Date(ev.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Actor: <span className="font-medium text-slate-700 dark:text-slate-300">{ev.actor}</span>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </article>
  );
}
