<script setup lang="ts">
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { extractErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const tab = ref<'login' | 'register'>('login')
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '', confirm: '' })

const isRegister = computed(() => tab.value === 'register')

const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名 3-32 位', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_]+$/,
      message: '只能包含字母、数字和下划线',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码 6-64 位', trigger: 'blur' },
  ],
  confirm: isRegister.value
    ? [
        { required: true, message: '请再次输入密码', trigger: 'blur' },
        {
          validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
            if (value !== form.password) {
              callback(new Error('两次输入的密码不一致'))
              return
            }
            callback()
          },
          trigger: 'blur',
        },
      ]
    : [],
}))

async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  try {
    if (isRegister.value) {
      await auth.register(form.username, form.password)
      ElMessage.success('注册成功，已自动登录')
    } else {
      await auth.login(form.username, form.password)
      ElMessage.success('登录成功')
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/chat'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
}

function switchTab(name: string | number): void {
  tab.value = name === 'register' ? 'register' : 'login'
  formRef.value?.clearValidate()
}
</script>

<template>
  <div class="login-page">
    <section class="login-intro">
      <h1>RAG 知识库智能问答</h1>
      <p class="slogan">向量 + BM25 双路召回，Cross-Encoder 重排，答案句句可溯源。</p>
      <ul class="feature-list">
        <li>结构感知切分：保留页码与章节层级</li>
        <li>混合检索 + RRF 融合：兼顾语义与精确术语</li>
        <li>流式回答 + 引用卡片：每句都能点回原文</li>
        <li>多用户隔离：会话与知识库互不可见</li>
      </ul>
    </section>

    <section class="login-card">
      <el-tabs :model-value="tab" class="tabs" @tab-change="switchTab">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="字母、数字或下划线" clearable />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少 6 位"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-form-item v-if="isRegister" label="确认密码" prop="confirm">
          <el-input
            v-model="form.confirm"
            type="password"
            placeholder="再输入一次密码"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="submit"
          :loading="auth.loading"
          @click="handleSubmit"
        >
          {{ isRegister ? '注册并登录' : '登录' }}
        </el-button>
      </el-form>

      <p class="tip">
        {{ isRegister ? '注册后会自动登录并进入问答页' : '首次使用请先切换到注册页创建账号' }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  gap: 64px;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  background:
    radial-gradient(circle at 15% 20%, #e8efff 0%, transparent 45%),
    radial-gradient(circle at 85% 75%, #eaf7f1 0%, transparent 45%),
    var(--rag-bg);
}

.login-intro {
  max-width: 430px;
}

.login-intro h1 {
  margin: 0 0 14px;
  font-size: 30px;
  line-height: 1.3;
}

.slogan {
  margin: 0 0 22px;
  font-size: 15px;
  line-height: 1.7;
  color: var(--rag-text-weak);
}

.feature-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.feature-list li {
  position: relative;
  padding-left: 22px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #4a5261;
}

.feature-list li::before {
  position: absolute;
  top: 7px;
  left: 0;
  width: 7px;
  height: 7px;
  content: '';
  background: var(--rag-primary);
  border-radius: 50%;
}

.login-card {
  width: 380px;
  padding: 28px 30px 22px;
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-radius: 14px;
  box-shadow: 0 12px 32px rgb(31 35 41 / 8%);
}

.tabs {
  margin-bottom: 6px;
}

.submit {
  width: 100%;
  margin-top: 4px;
}

.tip {
  margin: 16px 0 0;
  font-size: 12px;
  color: var(--rag-text-weak);
  text-align: center;
}

@media (width <= 900px) {
  .login-intro {
    display: none;
  }

  .login-page {
    padding: 20px;
  }
}
</style>