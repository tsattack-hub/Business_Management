import React, { useState } from 'react';
import ProjectPage from './components/ProjectPage';
import SpecPage from './components/SpecPage';
import BoqPage from './components/BoqPage';

const TAB_STYLE = (active) => ({
  padding: '0.55rem 1.3rem',
  borderRadius: '8px 8px 0 0',
  border: 'none',
  cursor: 'pointer',
  fontWeight: active ? 700 : 500,
  fontSize: '0.95rem',
  background: active ? 'var(--bg-secondary)' : 'transparent',
  color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
  borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
  transition: 'all 0.15s',
});

export default function App() {
  const [tab, setTab] = useState('project');

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <div style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-subtle)', padding: '0 1.5rem' }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', display: 'flex', alignItems: 'center', gap: '2rem' }}>
          <div style={{ padding: '1rem 0', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ fontSize: '1.4rem' }}>◧</span>
            <div>
              <div style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>구매설치</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 900, letterSpacing: '-0.02em', lineHeight: 1.2 }}>사업관리</div>
            </div>
          </div>
          <nav style={{ display: 'flex', gap: '0.25rem', alignSelf: 'flex-end' }}>
            <button style={TAB_STYLE(tab === 'project')} onClick={() => setTab('project')}>
              ◧ 사업 절차관리
            </button>
            <button style={TAB_STYLE(tab === 'spec')} onClick={() => setTab('spec')}>
              ▤ 구매규격서
            </button>
            <button style={TAB_STYLE(tab === 'boq')} onClick={() => setTab('boq')}>
              ◫ 내역서 검증
            </button>
          </nav>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '1.5rem' }}>
        {tab === 'project' && <ProjectPage />}
        {tab === 'spec' && <SpecPage />}
        {tab === 'boq' && <BoqPage />}
      </div>
    </div>
  );
}
