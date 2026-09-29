import { Link } from 'react-router-dom'
import {
  Inbox, KeyRound, ScanLine, ShieldCheck, Fingerprint, Bot,
  ArrowRight, Search, ListOrdered, UserCheck, Gavel, Banknote,
  Building2, FileSearch, Scale, Layers,
  AlertTriangle, HeartHandshake, DollarSign, XCircle, CheckCircle2,
  ClipboardCheck, TrendingUp, Target,
} from 'lucide-react'
import { APP_URLS } from '../config/appUrls'

// ── The app suite ────────────────────────────────────────────────────────────

interface AppCard {
  name: string; desc: string; icon: any; accent: string
  href?: string; internal?: boolean; current?: boolean
}

const APPS: AppCard[] = [
  { name: 'Intake Portal', accent: '#0ea5e9', icon: Inbox,
    desc: 'Where claims and documents enter — 837 intake, uploads, validation.',
    href: '/file-intake', internal: true },
  { name: 'IAM', accent: '#6366f1', icon: KeyRound,
    desc: 'Identity & access — who can do what across the whole suite.',
    href: APP_URLS.iam },
  { name: 'ClaimGuard', accent: '#f59e0b', icon: ScanLine,
    desc: 'Pre-pay review — catch overpayments before the money goes out.',
    href: APP_URLS.claimguard },
  { name: 'PayGuard', accent: '#FE017D', icon: ShieldCheck,
    desc: 'Post-pay integrity — recover overpayments already paid. (You are here.)',
    current: true },
  { name: 'SIU', accent: '#ef4444', icon: Fingerprint,
    desc: 'Special Investigations Unit — fraud, waste & abuse casework.',
    href: APP_URLS.siu },
  { name: 'Assistant', accent: '#10b981', icon: Bot,
    desc: 'AI copilot across the suite — ask questions, summarize, take action.',
    href: APP_URLS.assistant },
]

function AppBox({ app }: { app: AppCard }) {
  const Icon = app.icon
  const inner = (
    <div className={`h-full rounded-xl border p-4 transition-shadow ${
      app.current ? 'border-[#FE017D] bg-[#FE017D]/5 shadow-sm' : 'border-gray-200 bg-white hover:shadow-md'}`}>
      <div className="flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${app.accent}1a` }}>
          <Icon className="w-5 h-5" style={{ color: app.accent }} />
        </div>
        <div className="font-bold text-gray-900">{app.name}</div>
        {app.current && <span className="ml-auto text-[10px] font-bold text-[#FE017D] uppercase tracking-wider">current</span>}
      </div>
      <p className="text-xs text-gray-500 mt-2 leading-snug">{app.desc}</p>
    </div>
  )
  if (app.current) return inner
  if (app.internal && app.href) return <Link to={app.href} className="block h-full">{inner}</Link>
  if (app.href) return <a href={app.href} target="_blank" rel="noreferrer" className="block h-full">{inner}</a>
  return inner
}

// ── Flow primitives ──────────────────────────────────────────────────────────

function FlowStep({ icon: Icon, title, sub, accent = '#6b7280' }: { icon: any; title: string; sub: string; accent?: string }) {
  return (
    <div className="flex-1 min-w-[130px] rounded-xl border border-gray-200 bg-white p-3 text-center">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center mx-auto" style={{ backgroundColor: `${accent}1a` }}>
        <Icon className="w-5 h-5" style={{ color: accent }} />
      </div>
      <div className="text-sm font-semibold text-gray-900 mt-2">{title}</div>
      <div className="text-[11px] text-gray-500 mt-0.5 leading-snug">{sub}</div>
    </div>
  )
}

function Arrow() {
  return <ArrowRight className="w-5 h-5 text-gray-300 shrink-0 self-center rotate-90 sm:rotate-0" />
}

function SectionTitle({ eyebrow, title, desc }: { eyebrow: string; title: string; desc: string }) {
  return (
    <div className="mb-4">
      <div className="text-[11px] font-bold uppercase tracking-wider text-[#FE017D]">{eyebrow}</div>
      <h2 className="text-lg font-bold text-gray-900">{title}</h2>
      <p className="text-sm text-gray-500 mt-0.5">{desc}</p>
    </div>
  )
}

// ── Intro / business-case primitives ─────────────────────────────────────────

function StatCard({ value, label, source }: { value: string; label: string; source: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="text-2xl font-bold text-[#FE017D]">{value}</div>
      <div className="text-xs text-gray-700 mt-1 leading-snug">{label}</div>
      <div className="text-[10px] text-gray-400 mt-1.5">{source}</div>
    </div>
  )
}

function ImpactCard({
  icon: Icon, tone, title, points,
}: { icon: any; tone: 'red' | 'amber'; title: string; points: string[] }) {
  const c = tone === 'red'
    ? { bd: 'border-red-200',   bg: 'bg-red-50/60',   ic: '#ef4444', tx: 'text-red-900' }
    : { bd: 'border-amber-200', bg: 'bg-amber-50/60', ic: '#f59e0b', tx: 'text-amber-900' }
  return (
    <div className={`rounded-xl border ${c.bd} ${c.bg} p-4`}>
      <div className="flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${c.ic}1a` }}>
          <Icon className="w-5 h-5" style={{ color: c.ic }} />
        </div>
        <div className={`font-bold ${c.tx}`}>{title}</div>
      </div>
      <ul className="mt-3 space-y-1.5">
        {points.map((p) => (
          <li key={p} className="flex gap-2 text-xs text-gray-700 leading-snug">
            <span className="mt-1.5 w-1 h-1 rounded-full shrink-0" style={{ backgroundColor: c.ic }} />
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// A single "today's approach → where it falls short → how we close the gap" row.
function ShortfallRow({ approach, shortfall, ours }: { approach: string; shortfall: string; ours: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="rounded-xl border border-gray-200 bg-white p-3.5">
        <div className="flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-500 shrink-0" />
          <div className="text-sm font-semibold text-gray-900">{approach}</div>
        </div>
        <p className="text-xs text-gray-500 mt-1.5 leading-snug">{shortfall}</p>
      </div>
      <div className="rounded-xl border border-[#FE017D]/30 bg-[#FE017D]/5 p-3.5">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-[#FE017D] shrink-0" />
          <div className="text-sm font-semibold text-gray-900">How we address it</div>
        </div>
        <p className="text-xs text-gray-600 mt-1.5 leading-snug">{ours}</p>
      </div>
    </div>
  )
}

function OpsCard({ icon: Icon, title, desc }: { icon: any; title: string; desc: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: '#10b9811a' }}>
        <Icon className="w-5 h-5" style={{ color: '#10b981' }} />
      </div>
      <div className="text-sm font-semibold text-gray-900 mt-2.5">{title}</div>
      <p className="text-xs text-gray-500 mt-1 leading-snug">{desc}</p>
    </div>
  )
}

const SHORTFALLS = [
  {
    approach: 'Legacy rules-only edit engines',
    shortfall: 'Static code edits catch known patterns but miss novel schemes (false negatives) and over-flag borderline claims (false positives), driving provider abrasion.',
    ours: 'Deterministic rules are paired with two calibrated ML models, so novel high-risk claims still surface while low-value flags are down-ranked before they ever reach a provider.',
  },
  {
    approach: 'Black-box vendor scores',
    shortfall: 'Third-party "risk scores" are not explainable and rarely calibrated, so findings are hard to defend on appeal and impossible to prioritize by real dollar impact.',
    ours: 'Scores are probability-calibrated and every finding is backed by a cited, deterministic rule — defensible in an appeal and rankable by expected value ($ × probability).',
  },
  {
    approach: 'Manual / SQL-query audits',
    shortfall: 'Analyst-written queries and spreadsheets do not scale, sample only a fraction of claims, and leave a thin, hard-to-reconstruct audit trail.',
    ours: 'Every claim is scored automatically and the highest-yield cases are queued first, with an immutable audit log capturing each decision end to end.',
  },
  {
    approach: 'Pure pay-and-chase (post-pay only)',
    shortfall: 'Recovering money after it is paid is slow, costly, and strains provider relationships when clawbacks arrive months later.',
    ours: 'The same engine runs pre-pay (ClaimGuard) and post-pay (PayGuard) on one platform — stop overpayments before they go out, and recover what slips through.',
  },
]

// ── Page ─────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-10 py-2">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platform Overview</h1>
        <p className="text-sm text-gray-500 mt-1">
          A healthcare payment-integrity suite. Claims flow in, get scored and prioritized, are reviewed by analysts,
          and overpayments are recovered — with an AI/ML engine driving where attention goes.
        </p>
      </div>

      {/* 0 · The problem & business case */}
      <section className="space-y-8">
        <div>
          <SectionTitle eyebrow="Why this exists" title="The problem: billions leak out in overpayments"
            desc="Health plans pay out on millions of claims a year. A meaningful share are wrong — duplicates, upcoding, unbundling, non-covered or medically-unnecessary services, and outright fraud. At scale, small error rates become enormous dollars." />
          <p className="text-sm text-gray-600 leading-relaxed max-w-3xl">
            Payment integrity is the discipline of catching those errors — ideally before the money goes out, and
            recovering it when it does. The hard part isn't finding <em>something</em> wrong; it's finding the right
            things: enough coverage that real overpayments don't slip through, with enough precision that legitimate
            providers aren't buried in unwarranted clawbacks.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
            <StatCard value="$100B+" label="Estimated annual improper payments across Medicare & Medicaid" source="CMS / HHS Agency Financial Report, FY2023" />
            <StatCard value="$31.2B" label="Medicare fee-for-service improper payments (7.4% of spending)" source="CMS estimated improper payment rates, FY2023" />
            <StatCard value="$50.3B" label="Medicaid improper payments (8.6% of spending)" source="CMS estimated improper payment rates, FY2023" />
            <StatCard value="3–10%" label="Of total U.S. health spending lost to fraud, waste & abuse" source="National Health Care Anti-Fraud Association" />
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            Figures are publicly reported federal estimates.{' '}
            <a href="https://www.cms.gov/data-research/monitoring-programs/improper-payment-measurement-programs"
               target="_blank" rel="noreferrer" className="underline hover:text-gray-600">CMS improper-payment measurement</a>
            {' · '}
            <a href="https://www.nhcaa.org/" target="_blank" rel="noreferrer" className="underline hover:text-gray-600">NHCAA</a>.
            Improper payments include both overpayments and documentation errors, not all of which are recoverable.
          </p>
        </div>

        {/* Cost of getting it wrong — provider relations */}
        <div>
          <SectionTitle eyebrow="The cost of getting it wrong" title="Two failure modes, both expensive"
            desc="A payment-integrity program is judged on both sides of the confusion matrix. Missing a bad claim costs money; flagging a good one costs trust." />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ImpactCard icon={AlertTriangle} tone="red" title="Missed cases — false negatives"
              points={[
                'Recoverable dollars written off permanently — pure leakage to the bottom line.',
                'Regulatory and compliance exposure when improper payments go undetected.',
                'Repeat patterns go unaddressed, so the same overpayments recur month after month.',
                'Erodes plan integrity and audit readiness with regulators and CMS.',
              ]} />
            <ImpactCard icon={HeartHandshake} tone="amber" title="Mistakes — false positives"
              points={[
                'Wrongful recoupment demands damage provider relationships and network trust.',
                'Every disputed flag triggers appeals, rework, and administrative cost on both sides.',
                'Provider abrasion drives attrition and can jeopardize network adequacy.',
                'Reputational risk — a plan seen as clawing back unfairly loses provider goodwill.',
              ]} />
          </div>
          <p className="text-xs text-gray-500 mt-3 max-w-3xl leading-snug">
            The two are in tension: crank up sensitivity and you bury providers in false alarms; tighten it and you
            leave money on the table. The goal is a system that manages the trade-off deliberately rather than by luck.
          </p>
        </div>

        {/* Market landscape & shortfalls */}
        <div>
          <SectionTitle eyebrow="Today's tools" title="Where current solutions fall short"
            desc="Most payment-integrity stacks lean on one technique. Each has a real weakness — and our approach is built to close exactly those gaps." />
          <div className="space-y-3">
            {SHORTFALLS.map((s) => <ShortfallRow key={s.approach} {...s} />)}
          </div>
        </div>

        {/* Operational upside beyond revenue */}
        <div>
          <SectionTitle eyebrow="Beyond recovered dollars" title="Operational upside"
            desc="Added revenue is the headline, but the day-to-day wins compound — cleaner audits, stronger compliance, and analysts spending time where it pays off." />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <OpsCard icon={DollarSign} title="More recovered revenue" desc="Expected-value prioritization surfaces the highest-yield cases first, so recovery per analyst-hour goes up." />
            <OpsCard icon={ClipboardCheck} title="Easier audits" desc="Every decision is captured in an immutable audit log, so reconstructing what happened — and why — is trivial." />
            <OpsCard icon={ShieldCheck} title="Stronger compliance" desc="Findings are backed by cited, deterministic rules that are defensible on appeal and stand up to regulator scrutiny." />
            <OpsCard icon={TrendingUp} title="Higher analyst leverage" desc="Calibrated scoring cuts low-value reviews, so the team clears more real overpayments with the same headcount." />
          </div>
          <div className="rounded-xl border border-[#FE017D]/30 bg-[#FE017D]/5 p-4 mt-3 flex items-start gap-3">
            <Target className="w-5 h-5 text-[#FE017D] shrink-0 mt-0.5" />
            <p className="text-sm text-gray-700 leading-snug">
              <span className="font-semibold text-gray-900">Net effect:</span> catch more of what matters, flag fewer of
              what doesn't, and defend every decision — recovering more while protecting the provider relationships the
              plan depends on.
            </p>
          </div>
        </div>
      </section>

      {/* 1 · The suite */}
      <section>
        <SectionTitle eyebrow="The suite" title="Six apps, one backend"
          desc="Each app owns a slice of the payment-integrity lifecycle. PayGuard is the post-pay recovery app." />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {APPS.map((a) => <AppBox key={a.name} app={a} />)}
        </div>
      </section>

      {/* 2 · User workflow */}
      <section>
        <SectionTitle eyebrow="User workflow" title="How a case moves"
          desc="The analyst's journey — from a claim arriving to money recovered." />
        <div className="flex flex-col sm:flex-row gap-2 items-stretch">
          <FlowStep icon={Inbox} accent="#0ea5e9" title="Claim arrives" sub="Adjudicated claim + documents land via intake." />
          <Arrow />
          <FlowStep icon={Search} accent="#f59e0b" title="Detect" sub="~23 rules + AI clinical rules flag issues." />
          <Arrow />
          <FlowStep icon={ListOrdered} accent="#FE017D" title="Prioritize" sub="Ranked by expected value ($ × probability)." />
          <Arrow />
          <FlowStep icon={UserCheck} accent="#6366f1" title="Review" sub="Analyst opens the case, weighs the evidence." />
          <Arrow />
          <FlowStep icon={Gavel} accent="#8b5cf6" title="Decide" sub="Recoup, clear, or escalate to SIU." />
          <Arrow />
          <FlowStep icon={Banknote} accent="#10b981" title="Recover" sub="Notice sent, funds recouped, case closed." />
        </div>
      </section>

      {/* 3 · Pipeline flow */}
      <section>
        <SectionTitle eyebrow="The engine" title="How a claim gets scored — the ML pipeline"
          desc="Two calibrated models decide where analyst time is worth spending; the rules then confirm what's recoverable." />
        <div className="flex flex-col sm:flex-row gap-2 items-stretch">
          <FlowStep icon={Building2} accent="#6366f1" title="Stage 1 · Provider Reputation" sub="Scores each provider's billing behavior → P_risk (calibrated)." />
          <Arrow />
          <FlowStep icon={Layers} accent="#FE017D" title="Stage 2 · Claim Predictor" sub="Scores each claim from payment features + P_risk → calibrated probability." />
          <Arrow />
          <FlowStep icon={Scale} accent="#0ea5e9" title="Prioritize by EV" sub="probability × dollars, cut to team capacity." />
          <Arrow />
          <FlowStep icon={FileSearch} accent="#f59e0b" title="Rules confirm" sub="Deterministic + AI rules produce defensible findings." />
          <Arrow />
          <FlowStep icon={UserCheck} accent="#10b981" title="Case worked" sub="Analyst reviews the highest-yield cases first." />
        </div>
        <p className="text-[11px] text-gray-400 mt-3">
          The models decide <span className="font-medium text-gray-500">where to look</span> (probabilistic, calibrated);
          the rules decide <span className="font-medium text-gray-500">what's recoverable</span> (deterministic, cited).
          Stage 1's score feeds Stage 2 as a feature — that cross-stage handoff is what makes claim scoring provider-aware.
        </p>
      </section>
    </div>
  )
}
