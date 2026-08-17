import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  analyzeProject,
  deleteProject,
  downloadAllZip,
  downloadDocument,
  getBlank,
  getProject,
  listProjects,
  saveProject,
} from '../services/api';
import { Num, Text } from './fields';

// ─── 스타일 ─────────────────────────────────────────────────────────────────────

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
  btn: (variant) => ({
    padding: '0.5rem 0.9rem',
    borderRadius: 8,
    border: variant === 'ghost' ? '1px solid var(--border-subtle)' : 'none',
    cursor: 'pointer',
    fontSize: '0.85rem',
    fontWeight: 600,
    width: '100%',
    background: variant === 'primary' ? 'var(--accent)'
      : variant === 'danger' ? 'transparent' : 'var(--bg-tertiary)',
    color: variant === 'danger' ? 'var(--danger)' : '#fff',
    ...(variant === 'danger' ? { border: '1px solid var(--danger)' } : {}),
  }),
  trap: {
    borderLeft: '3px solid var(--brick)', background: 'var(--brick-bg)', color: '#fca5a5',
    padding: '0.55rem 0.8rem', margin: '0.35rem 0', fontSize: '0.82rem', lineHeight: 1.6, borderRadius: 4,
  },
  cite: { fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' },
};

const CONDITIONS = [
  ['설치작업있음', '설치작업 있음'], ['CCTV설치', '영상정보처리기기(CCTV)'],
  ['중기간경쟁제품', '중기간경쟁제품'], ['시설물신축_증개축', '시설물 신축·증개축'],
  ['정보통신제품도입', '정보통신제품 도입'], ['정보화사업', '정보화사업'],
  ['소프트웨어포함', '소프트웨어 포함'], ['방송장비', '방송장비'],
  ['관급자재있음', '관급자재 있음'], ['예비품있음', '예비품 입고'],
];

const BID_METHODS = ['계약이행능력심사', '협상에 의한 계약', '전자공개수의계약'];

function won(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `${n.toLocaleString()}원` : '-';
}

// ─── 메인 ───────────────────────────────────────────────────────────────────────

export default function ProjectPage() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState(null);          // 저장된 사업 id (신규면 null)
  const [proj, setProj] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [msg, setMsg] = useState(null);          // {kind, text}
  const [busyDoc, setBusyDoc] = useState('');
  const [zipInfo, setZipInfo] = useState(null);
  const debounceRef = useRef();

  const refreshList = useCallback(async () => {
    try { setProjects(await listProjects()); } catch { /* 무시 */ }
  }, []);

  useEffect(() => {
    (async () => {
      await refreshList();
      try { setProj(await getBlank()); } catch { setProj({}); }
    })();
  }, [refreshList]);

  // 구조에 영향을 주는 필드가 바뀌면 분석을 다시 돌린다 (디바운스)
  useEffect(() => {
    if (!proj || !proj['사업명']) { setAnalysis(null); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setAnalyzing(true);
      try { setAnalysis(await analyzeProject(proj)); }
      catch { setAnalysis(null); }
      finally { setAnalyzing(false); }
    }, 350);
    return () => clearTimeout(debounceRef.current);
  }, [
    proj?.['사업명'], proj?.['연도'], proj?.['추정가격'],
    proj?.['물품분'], proj?.['설치분_노무'], proj?.['설치분_경비'],
    proj?.['낙찰방법'],
    ...CONDITIONS.map(([k]) => proj?.[k]),
  ]);

  const set = useCallback((k, v) => setProj(p => ({ ...p, [k]: v })), []);

  const done = new Set(proj?.['완료태스크'] || []);
  const toggleTask = useCallback((tid) => {
    setProj(p => {
      const cur = new Set(p['완료태스크'] || []);
      cur.has(tid) ? cur.delete(tid) : cur.add(tid);
      return { ...p, '완료태스크': [...cur] };
    });
  }, []);

  const onPick = useCallback(async (value) => {
    setMsg(null); setZipInfo(null);
    if (value === '__new__') {
      setPid(null);
      try { setProj(await getBlank()); } catch { setProj({}); }
      return;
    }
    try {
      const loaded = await getProject(value);
      setProj(loaded);
      setPid(value);
    } catch { setMsg({ kind: 'error', text: '사업을 불러오지 못했습니다.' }); }
  }, []);

  const onSave = useCallback(async () => {
    if (!proj?.['사업명']) { setMsg({ kind: 'error', text: '사업명을 입력하세요.' }); return; }
    try {
      const { id } = await saveProject(proj);
      setPid(id);
      await refreshList();
      setMsg({ kind: 'ok', text: '저장했습니다.' });
    } catch (e) {
      setMsg({ kind: 'error', text: '저장 실패: ' + (e.response?.data?.detail || e.message) });
    }
  }, [proj, refreshList]);

  const onDelete = useCallback(async () => {
    if (!pid) return;
    await deleteProject(pid);
    setPid(null);
    await refreshList();
    try { setProj(await getBlank()); } catch { setProj({}); }
    setMsg({ kind: 'ok', text: '삭제했습니다.' });
  }, [pid, refreshList]);

  const onDoc = useCallback(async (docId, name) => {
    setBusyDoc(docId);
    try { await downloadDocument(docId, proj); }
    catch (e) { setMsg({ kind: 'error', text: `${name} 생성 실패: ` + (e.response?.data?.detail || e.message) }); }
    finally { setBusyDoc(''); }
  }, [proj]);

  const onZip = useCallback(async () => {
    setZipInfo({ loading: true });
    try {
      const { made } = await downloadAllZip(proj);
      setZipInfo({ made });
    } catch (e) {
      setZipInfo(null);
      setMsg({ kind: 'error', text: '일괄 생성 실패: ' + (e.response?.data?.detail || e.message) });
    }
  }, [proj]);

  if (!proj) return <div style={{ color: 'var(--text-secondary)' }}>불러오는 중…</div>;

  const j = analysis?.judgment;
  const inScope = j?.inScope;
  const allTaskIds = new Set((analysis?.stages || []).flatMap(s => s.tasks.map(t => t.id)));
  const doneCount = [...done].filter(id => allTaskIds.has(id)).length;
  const total = analysis?.totalTasks || 0;

  return (
    <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
      {/* ── 사이드바 ── */}
      <aside style={{ width: 320, flexShrink: 0 }}>
        <div style={S.card}>
          <div style={{ ...S.sideTitle, marginTop: 0 }}>사업</div>
          <select value={pid ?? '__new__'} onChange={e => onPick(e.target.value)}>
            <option value="__new__">＋ 새 사업</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <div style={S.sideTitle}>기본 정보</div>
          <Text label="사업명" value={proj['사업명']} onChange={v => set('사업명', v)} />
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Num label="연도" value={proj['연도']} onChange={v => set('연도', v)} />
            <Text label="공항" value={proj['공항']} onChange={v => set('공항', v)} />
          </div>
          <Text label="주관부서" value={proj['부서']} onChange={v => set('부서', v)} />
          <Text label="담당자" value={proj['담당자']} onChange={v => set('담당자', v)} />
          <Num label="추정가격 (VAT 제외)" value={proj['추정가격']} step={1000000} onChange={v => set('추정가격', v)} />
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Num label="이행기간(일)" value={proj['이행기간']} onChange={v => set('이행기간', v)} />
            <Text label="준공목표" type="date"
              value={typeof proj['목표준공일'] === 'string' ? proj['목표준공일'] : ''}
              onChange={v => set('목표준공일', v)} />
          </div>

          <div style={S.sideTitle}>설계금액 · 계약유형 판정용</div>
          <Num label="재료비 (물품분)" value={proj['물품분']} step={1000000} onChange={v => set('물품분', v)} />
          <Num label="직접노무비 (설치분)" value={proj['설치분_노무']} step={1000000} onChange={v => set('설치분_노무', v)} />
          <Num label="경비 (설치분)" value={proj['설치분_경비']} step={1000000} onChange={v => set('설치분_경비', v)} />

          <div style={S.sideTitle}>사업 조건 · 체크한 것만 절차에 반영</div>
          {CONDITIONS.map(([k, lbl]) => (
            <label key={k} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.15rem 0', fontSize: '0.82rem', color: 'var(--text-primary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={!!proj[k]} onChange={e => set(k, e.target.checked)} />
              {lbl}
            </label>
          ))}

          <div style={S.sideTitle}>낙찰방법</div>
          <select value={proj['낙찰방법'] || BID_METHODS[0]} onChange={e => set('낙찰방법', e.target.value)}>
            {BID_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button style={S.btn('primary')} onClick={onSave}>저장</button>
            {pid && <button style={S.btn('danger')} onClick={onDelete}>삭제</button>}
          </div>
          {msg && (
            <div style={{ marginTop: '0.6rem', fontSize: '0.8rem', color: msg.kind === 'error' ? 'var(--danger)' : 'var(--success)' }}>
              {msg.text}
            </div>
          )}
        </div>
      </aside>

      {/* ── 본문 ── */}
      <main style={{ flex: 1, minWidth: 0 }}>
        {!proj['사업명'] && (
          <div style={{ ...S.card, color: 'var(--text-secondary)' }}>
            좌측에서 사업명을 입력하면 시작합니다. 설계금액 세 칸을 채우면 계약유형이 판정됩니다.
          </div>
        )}

        {proj['사업명'] && (
          <>
            {/* 판정 배너 */}
            <div style={{ ...S.card, borderLeft: `4px solid ${inScope ? 'var(--accent)' : 'var(--brick)'}` }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', color: 'var(--text-tertiary)' }}>
                판정 {analyzing && '· 분석 중…'}
              </div>
              {j ? (
                <>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, marginTop: '0.2rem', color: inScope ? 'var(--text-primary)' : 'var(--brick)' }}>
                    {j.kind} · 설치비중 {j.ratioPct}
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                    {proj['사업명']}
                    {analysis?.track ? ` · ${analysis.track.value}` : ''}
                    {` · ${proj['낙찰방법'] || BID_METHODS[0]} · 추정가격 ${won(proj['추정가격'])}`}
                  </div>
                  {j.notes?.map((n, i) => <div key={i} style={S.trap}>{n}</div>)}
                </>
              ) : (
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.3rem' }}>
                  설계금액을 입력하면 계약유형을 판정합니다.
                </div>
              )}
            </div>

            {j && !inScope && (
              <div style={{ ...S.card, color: 'var(--warning)' }}>
                {j.kind === '판정불가'
                  ? '설계금액 합계가 0입니다. 금액을 입력하세요.'
                  : '공사계약이므로 이 절차의 적용 범위를 벗어납니다.'}
              </div>
            )}

            {/* 진행률 + 단계 */}
            {inScope && analysis?.stages?.length > 0 && (
              <>
                <div style={S.card}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                    <span>진행 상태</span>
                    <span>{doneCount} / {total} 태스크</span>
                  </div>
                  <div style={{ height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${total ? (doneCount / total) * 100 : 0}%`, background: 'var(--accent)', transition: 'width 0.2s' }} />
                  </div>
                </div>

                {analysis.stages.map((stage, si) => (
                  <StageBlock
                    key={stage.id}
                    stage={stage}
                    defaultOpen={si === 0}
                    done={done}
                    onToggle={toggleTask}
                    onDoc={onDoc}
                    busyDoc={busyDoc}
                  />
                ))}

                {/* 일괄 생성 */}
                <div style={{ ...S.card, display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <button style={{ ...S.btn('primary'), width: 'auto' }} onClick={onZip} disabled={zipInfo?.loading}>
                    {zipInfo?.loading ? '생성 중…' : '전체 서류 틀 한 번에 만들기 (zip)'}
                  </button>
                  {zipInfo && !zipInfo.loading && (
                    <span style={{ color: 'var(--success)', fontSize: '0.82rem' }}>
                      서류 {zipInfo.made ?? ''}종을 내려받았습니다.
                    </span>
                  )}
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>
                    한글 문서는 .hwpx 로 만들어집니다. 「( 작성 필요 )」 표시는 사람이 판단할 항목입니다.
                  </span>
                </div>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ─── 단계 블록 ─────────────────────────────────────────────────────────────────

function StageBlock({ stage, defaultOpen, done, onToggle, onDoc, busyDoc }) {
  const nDone = stage.tasks.filter(t => done.has(t.id)).length;
  return (
    <details open={defaultOpen} style={S.card}>
      <summary style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 700 }}>
        <span>{stage.id[1]}. {stage.name}</span>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', fontWeight: 500 }}>
          {nDone}/{stage.tasks.length} 완료 · 서류 {stage.docs.length}종
        </span>
      </summary>

      <div style={{ marginTop: '0.8rem' }}>
        {stage.cautions.length > 0 && (
          <div style={{ marginBottom: '0.8rem' }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              이 단계에서 조심할 것
            </div>
            {stage.cautions.map((c, i) => (
              <div key={i} style={S.trap}>
                {c.text}
                {(c.source || c.citation) && (
                  <div style={S.cite}>{[c.source, c.citation].filter(Boolean).join(' · ')}</div>
                )}
              </div>
            ))}
          </div>
        )}

        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>할 일</div>
        {stage.tasks.map(t => (
          <div key={t.id} style={{ padding: '0.25rem 0' }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.86rem', cursor: 'pointer' }}>
              <input type="checkbox" checked={done.has(t.id)} onChange={() => onToggle(t.id)} style={{ marginTop: '0.2rem' }} />
              <span>{t.name}</span>
            </label>
            {(t.deadline || t.period || t.documents?.length > 0) && (
              <div style={{ ...S.cite, marginLeft: '1.5rem' }}>
                {[
                  t.deadline && `시점 ${t.deadline}`,
                  t.period && `주기 ${t.period}`,
                  t.documents?.length > 0 && `징구 ${t.documents.slice(0, 4).join(', ')}${t.documents.length > 4 ? ' 외' : ''}`,
                ].filter(Boolean).join(' · ')}
              </div>
            )}
          </div>
        ))}

        {stage.docs.length > 0 && (
          <>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', margin: '0.8rem 0 0.3rem' }}>작성할 서류</div>
            {stage.docs.map(d => (
              <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.8rem', padding: '0.35rem 0', borderTop: '1px solid var(--border-subtle)' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                    {d.name} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· {d.fmt}</span>
                  </div>
                  {d.note && <div style={S.cite}>{d.note}</div>}
                  {d.citation && <div style={S.cite}>{d.citation}</div>}
                </div>
                <button
                  onClick={() => onDoc(d.id, d.name)}
                  disabled={busyDoc === d.id}
                  style={{ flexShrink: 0, padding: '0.35rem 0.7rem', borderRadius: 6, border: '1px solid var(--border-subtle)', background: 'var(--bg-tertiary)', color: '#fff', cursor: 'pointer', fontSize: '0.78rem' }}
                >
                  {busyDoc === d.id ? '생성 중…' : '틀 만들기'}
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </details>
  );
}
