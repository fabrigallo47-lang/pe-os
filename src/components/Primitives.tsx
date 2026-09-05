import React from 'react';

export function PageLead({
  kicker,
  title,
  subtitle,
  side,
}: {
  kicker?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  side?: React.ReactNode;
}) {
  return <section className="p-page-lead">
    <div className="p-page-lead-main">
      {kicker && <div className="p-kicker">{kicker}</div>}
      <div className="p-reading" style={{marginTop:kicker?8:0}}>{title}</div>
      {subtitle && <div className="p-subtitle">{subtitle}</div>}
    </div>
    {side && <aside className="p-page-lead-side">{side}</aside>}
  </section>;
}

export function SectionLabel({children,meta}:{children:React.ReactNode;meta?:React.ReactNode}) {
  return <div style={{display:'flex',justifyContent:'space-between',gap:14,alignItems:'baseline'}}>
    <strong>{children}</strong>{meta&&<span className="p-meta">{meta}</span>}
  </div>;
}

export function MetaLine({children}:{children:React.ReactNode}) {
  return <div className="p-meta">{children}</div>;
}

export function EmptyValue({children='Not yet established'}:{children?:React.ReactNode}) {
  return <span className="p-muted">{children}</span>;
}

export function BeforeAfter({before,after}:{before?:React.ReactNode;after?:React.ReactNode}) {
  return <div className="p-impact-diff">
    <div className="p-muted">{before ?? '—'}</div>
    <span className="p-meta">→</span>
    <div>{after ?? '—'}</div>
  </div>;
}
