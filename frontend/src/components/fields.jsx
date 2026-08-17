import React from 'react';

// 사업 정보 입력에 공용으로 쓰는 작은 입력 컴포넌트.
// ProjectPage · SpecPage 가 함께 쓴다.

const FIELD = { marginBottom: '0.7rem' };
const LABEL = { display: 'block', marginBottom: '0.2rem', fontSize: '0.78rem', color: 'var(--text-secondary)' };

export function Text({ label, value, onChange, type = 'text' }) {
  return (
    <div style={FIELD}>
      <label style={LABEL}>{label}</label>
      <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)} />
    </div>
  );
}

export function Num({ label, value, onChange, step = 1 }) {
  return (
    <div style={FIELD}>
      <label style={LABEL}>{label}</label>
      <input
        type="number" step={step} value={value ?? 0}
        onChange={e => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
      />
    </div>
  );
}
