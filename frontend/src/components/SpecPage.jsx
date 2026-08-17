import React, { useCallback, useEffect, useState } from 'react';
import { getBlank, getProject, listProjects } from '../services/api';
import { Num, Text } from './fields';
import SpecGenPanel from './SpecGenPanel';

const S = {
  card: {
    background: 'var(--bg-secondary)',
    borderRadius: 12,
    border: '1px solid var(--border-subtle)',
    padding: '1.2rem 1.4rem',
    marginBottom: '1rem',
  },
  sideTitle: {
    fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase',
    color: 'var(--text-tertiary)', margin: '1.1rem 0 0.5rem',
  },
};

// 규격서 초안은 사업 정보(사업명·공항·추정가격 등)를 치환자로 쓴다.
// 저장된 사업을 불러오거나, 여기서 직접 입력해서 쓸 수 있다.
export default function SpecPage() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState(null);
  const [proj, setProj] = useState(null);

  useEffect(() => {
    (async () => {
      try { setProjects(await listProjects()); } catch { /* 무시 */ }
      try { setProj(await getBlank()); } catch { setProj({}); }
    })();
  }, []);

  const set = useCallback((k, v) => setProj(p => ({ ...p, [k]: v })), []);

  const onPick = useCallback(async (value) => {
    if (value === '__new__') {
      setPid(null);
      try { setProj(await getBlank()); } catch { setProj({}); }
      return;
    }
    try {
      setProj(await getProject(value));
      setPid(value);
    } catch { /* 무시 */ }
  }, []);

  if (!proj) return <div style={{ color: 'var(--text-secondary)' }}>불러오는 중…</div>;

  return (
    <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
      {/* ── 사이드바: 사업 선택 + 기본 정보 ── */}
      <aside style={{ width: 320, flexShrink: 0 }}>
        <div style={S.card}>
          <div style={{ ...S.sideTitle, marginTop: 0 }}>사업</div>
          <select value={pid ?? '__new__'} onChange={e => onPick(e.target.value)}>
            <option value="__new__">＋ 직접 입력</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.4rem', lineHeight: 1.5 }}>
            저장된 사업을 고르면 규격서에 사업 정보가 자동으로 채워집니다.
            여기서 값을 고쳐도 사업 정보에는 반영되지 않습니다.
          </div>

          <div style={S.sideTitle}>기본 정보 · 규격서 머리말에 들어감</div>
          <Text label="사업명" value={proj['사업명']} onChange={v => set('사업명', v)} />
          <Text label="공항" value={proj['공항']} onChange={v => set('공항', v)} />
          <Text label="주관부서" value={proj['부서']} onChange={v => set('부서', v)} />
          <Text label="담당자" value={proj['담당자']} onChange={v => set('담당자', v)} />
          <Num label="추정가격 (VAT 제외)" value={proj['추정가격']} step={1000000} onChange={v => set('추정가격', v)} />
          <Num label="이행기간(일)" value={proj['이행기간']} onChange={v => set('이행기간', v)} />

          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0 0', fontSize: '0.82rem', color: 'var(--text-primary)', cursor: 'pointer' }}>
            <input type="checkbox" checked={!!proj['설치작업있음']} onChange={e => set('설치작업있음', e.target.checked)} />
            설치작업 있음 (안전관리 조항 포함)
          </label>
        </div>
      </aside>

      {/* ── 본문: 규격서 초안 ── */}
      <main style={{ flex: 1, minWidth: 0 }}>
        {!proj['사업명'] ? (
          <div style={{ ...S.card, color: 'var(--text-secondary)' }}>
            좌측에서 사업을 고르거나 사업명을 입력하면 규격서 초안을 만들 수 있습니다.
          </div>
        ) : (
          <SpecGenPanel project={proj} />
        )}
      </main>
    </div>
  );
}
