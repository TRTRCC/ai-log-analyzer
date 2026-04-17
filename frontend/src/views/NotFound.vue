<template>
  <div class="page-container text-center">
    <el-result icon="404" title="404" sub-title="Page not found">
      <template #extra>
        <el-button type="primary" @click="goHome">Back to Dashboard</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/dashboard')
}
</script>