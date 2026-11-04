<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <span class="logo">RAG</span>
        <span class="brand-text">知识库智能问答</span>
      </div>

      <nav class="nav">
        <router-link to="/chat" class="nav-item" active-class="active">智能问答</router-link>
        <router-link to="/documents" class="nav-item" active-class="active">知识库</router-link>
      </nav>
    </header>

    <main class="app-body">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-header {
  display: flex;
  flex-shrink: 0;
  gap: 32px;
  align-items: center;
  height: 56px;
  padding: 0 20px;
  background: var(--rag-panel);
  border-bottom: 1px solid var(--rag-border);
}

.brand {
  display: flex;
  gap: 10px;
  align-items: center;
}

.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #3a6ff7, #6a9cff);
  border-radius: 9px;
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
}

.nav {
  display: flex;
  gap: 6px;
}

.nav-item {
  padding: 6px 14px;
  font-size: 14px;
  color: var(--rag-text-weak);
  border-radius: 8px;
  transition: all 0.15s ease;
}

.nav-item:hover {
  color: var(--rag-text);
  background: #f2f4f9;
}

.nav-item.active {
  color: var(--rag-primary);
  background: #eef3ff;
}

.app-body {
  flex: 1;
  min-height: 0;
}
</style>
