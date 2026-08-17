import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildSpecDraft, downloadSpecDocument, getSpecItemGroups } from '../services/api';
import HarvestPanel from './HarvestPanel';

// ─── 스타일 ─────────────────────────────────────────────────────────────────────

const S = {
  card: {
    background: 'var(--bg-secondary)',
    borderRadius: 12,
    border: '1px solid var(--border-subtle)',
    padding: '1.2rem 1.4rem',
    marginBottom: '1rem',
  },
  title: {
    fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em',
    textTransform: 'uppercase', color: 'var(--text-tertiary)',
  },
  subTitle: {
    fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)',
    margin: '1rem 0 0.4rem',
  },
  label: { display: 'block', marginBottom: '0.2rem', fontSize: '0.78rem', color: 'var(--text-secondary)' },
  req: { color: 'var(--brick)', marginLeft: '0.2rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.6rem 0.9rem' },
  unit: { fontSize: '0.72rem', color: 'var(--text-tertiary)', marginLeft: '0.3rem' },
  trap: {
    borderLeft: '3px solid var(--brick)', background: 'var(--brick-bg)', color: '#fca5a5',
    padding: '0.55rem 0.8rem', margin: '0.35rem 0', fontSize: '0.82rem', lineHeight: 1.6, borderRadius: 4,
  },
  info: {
    borderLeft: '3px solid var(--accent)', background: 'var(--bg-tertiary)', color: 'var(--text-secondary)',
    padding: '0.5rem 0.8rem', margin: '0.3rem 0', fontSize: '0.82rem', lineHeight: 1.6, borderRadius: 4,
  },
  cite: { fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' },
  btn: {
    padding: '0.5rem 0.9rem', borderRadius: 8, border: 'none', cursor: 'pointer',
    fontSize: '0.85rem', fontWeight: 600, background: 'var(--accent)', color: '#fff', width: 'auto',
  },
  pre: {
    whiteSpace: 'pre-wrap', fontSize: '0.78rem', lineHeight: 1.6, color: 'var(--text-primary)',
    background: 'var(--bg-tertiary)', borderRadius: 8, padding: '0.8rem 1rem', margin: '0.5rem 0 0',
    maxHeight: 420, overflow: 'auto',
  },
};

// 초안 조립에 영향을 주는 사업 필드. 이 값들이 바뀌면 초안을 다시 조립한다.
const RELEVANT = ['사업명', '공항', '부서', '담당자', '연도', '추정가격', '이행기간', '목표준공일', '설치작업있음'];

function SourceBadge({ source }) {
  const color = source === '표준' ? 'var(--success)' : source === '수집' ? 'var(--brick)' : 'var(--warning)';
  return (
    <span style={{ fontSize: '0.68rem', fontWeight: 700, color, border: `1px solid ${color}`, borderRadius: 4, padding: '0 0.3rem', marginLeft: '0.4rem' }}>
      {source}
    </span>
  );
}

// ─── 메인 ───────────────────────────────────────────────────────────────────────

export default function SpecGenPanel({ project }) {
  const [groups, setGroups] = useState([]);
  const [groupId, setGroupId] = useState('');
  const [specValues, setSpecValues] = useState({});
  const [extraClauses, setExtraClauses] = useState([]);   // 조달청에서 골라온 조항
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef();

  // 품목군 목록 로드
  useEffect(() => {
    (async () => {
      try {
        const gs = await getSpecItemGroups();
        setGroups(gs);
        if (gs.length > 0) setGroupId(prev => prev || gs[0].id);
      } catch {
        setError('품목군 목록을 불러오지 못했습니다.');
      }
    })();
  }, []);

  const group = useMemo(() => groups.find(g => g.id === groupId) || null, [groups, groupId]);

  // 초안 조립에 쓰는 사업 필드만 추려 의존성 키로 만든다 (사이드바 키 입력마다 재조립 방지)
  const projKey = useMemo(() => JSON.stringify(RELEVANT.map(k => project?.[k] ?? null)), [project]);
  const specKey = useMemo(() => JSON.stringify(specValues), [specValues]);
  const extraKey = useMemo(() => JSON.stringify(extraClauses), [extraClauses]);

  // 품목군·규격 수치·사업 정보가 바뀌면 초안을 다시 조립한다 (디바운스)
  useEffect(() => {
    if (!groupId || !project?.['사업명']) { setDraft(null); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        setDraft(await buildSpecDraft(groupId, project, specValues, extraClauses));
      } catch (e) {
        setDraft(null);
        setError('초안 생성 실패: ' + (e.response?.data?.detail || e.message));
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, specKey, projKey, extraKey]);

  const setValue = useCallback((key, v) => setSpecValues(prev => ({ ...prev, [key]: v })), []);

  const onGenerate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadSpecDocument(groupId, project, specValues, extraClauses);
    } catch (e) {
      setError('규격서 생성 실패: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBusy(false);
    }
  }, [groupId, project, specValues, extraClauses]);

  if (!project?.['사업명']) return null;

  const hits = draft?.brandHits || [];
  const blanks = draft?.blanks || [];

  return (
    <div style={S.card}>
      <div style={S.title}>구매규격서 초안 {loading && '· 조립 중…'}</div>

      {/* 품목군 선택 */}
      <div style={S.subTitle}>품목군</div>
      <select value={groupId} onChange={e => setGroupId(e.target.value)}>
        {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
      </select>

      {/* 규격 수치 입력 */}
      {group && group.specFields.length > 0 && (
        <>
          <div style={S.subTitle}>규격 수치 · 값을 넣으면 조항에 채워집니다. 비우면 「 」로 남습니다.</div>
          <div style={S.grid}>
            {group.specFields.map(f => (
              <div key={f.key}>
                <label style={S.label}>
                  {f.key}
                  {f.unit && <span style={S.unit}>({f.unit})</span>}
                  {f.required && <span style={S.req}>*</span>}
                </label>
                <input
                  type="text"
                  placeholder={f.hint || ''}
                  value={specValues[f.key] ?? ''}
                  onChange={e => setValue(f.key, e.target.value)}
                />
              </div>
            ))}
          </div>
        </>
      )}

      {/* 필수확인 */}
      {group && group.mustCheck.length > 0 && (
        <>
          <div style={S.subTitle}>이 품목에서 반드시 확인할 것</div>
          {group.mustCheck.map((m, i) => <div key={i} style={S.info}>{m}</div>)}
        </>
      )}

      {/* 조달청 유사 규격서 검토 → 고른 조항을 초안에 접붙임 */}
      <HarvestPanel defaultKeyword={project?.['사업명']} onSelect={setExtraClauses} />
      {extraClauses.length > 0 && (
        <div style={{ ...S.info, borderLeftColor: 'var(--warning)', color: 'var(--warning)' }}>
          조달청 수집 조항 {extraClauses.length}개가 초안에 포함됩니다 — 모두 「수집(검토 필요)」로 표시되며
          상표·특정기관 조건을 반드시 확인하세요.
        </div>
      )}

      {/* 특정회사 규격 경고 */}
      {hits.length > 0 && (
        <>
          <div style={S.subTitle}>특정회사 규격으로 의심되는 문구 {hits.length}건</div>
          {hits.map((h, i) => (
            <div key={i} style={S.trap}>
              <strong>{h.term}</strong> — {h.kind}
              {h.mitigated && <span style={{ color: 'var(--warning)' }}> · 「동등 이상」 문구 있음(그것만으로는 면책 안 됨)</span>}
              <div style={S.cite}>{h.where} — “{h.line}”</div>
            </div>
          ))}
          <div style={S.cite}>
            상표·모델은 성능 수치로 바꿔 쓰는 것이 원칙입니다. 불가피하면 규격서에 사유를 명시하십시오 (AUD-013).
          </div>
        </>
      )}
      {draft && hits.length === 0 && (
        <div style={{ ...S.info, borderLeftColor: 'var(--success)', color: 'var(--success)' }}>
          특정회사 규격으로 의심되는 문구가 발견되지 않았습니다.
        </div>
      )}

      {error && <div style={{ color: 'var(--danger)', fontSize: '0.82rem', marginTop: '0.6rem' }}>{error}</div>}

      {/* 미리보기 + 생성 */}
      {draft && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginTop: '1rem' }}>
            <button style={S.btn} onClick={onGenerate} disabled={busy}>
              {busy ? '생성 중…' : '규격서 초안 만들기 (.hwpx)'}
            </button>
            <span style={S.cite}>
              조항 {draft.clauseCount}개 · 채워야 할 항목 {blanks.length}곳
              {draft.sourceCounts && ` · ` + Object.entries(draft.sourceCounts).map(([k, v]) => `${k} ${v}`).join(', ')}
            </span>
          </div>

          <details style={{ marginTop: '0.6rem' }}>
            <summary style={{ cursor: 'pointer', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              본문 미리보기
            </summary>
            <pre style={S.pre}>{draft.text}</pre>
          </details>
        </>
      )}
    </div>
  );
}
