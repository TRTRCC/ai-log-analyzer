<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">Dashboard</h2>
      <p class="page-desc">System overview and statistics</p>
    </div>

    <!-- Statistics Cards -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ stats.totalLogs }}</div>
          <div class="stat-label">Total Logs</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card success">
          <div class="stat-value">{{ stats.todayLogs }}</div>
          <div class="stat-label">Today's Logs</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card warning">
          <div class="stat-value">{{ stats.errorCount }}</div>
          <div class="stat-label">Error Events</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card info">
          <div class="stat-value">{{ stats.aiTasks }}</div>
          <div class="stat-label">AI Analyses</div>
        </div>
      </el-col>
    </el-row>

    <!-- Charts Row -->
    <el-row :gutter="20" class="mt-20">
      <el-col :span="12">
        <div class="chart-container">
          <div ref="logTrendChart" style="height: 350px;"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="chart-container">
          <div ref="errorDistributionChart" style="height: 350px;"></div>
        </div>
      </el-col>
    </el-row>

    <!-- Recent Analysis -->
    <el-row :gutter="20" class="mt-20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>Recent AI Analysis Tasks</span>
          </template>
          <el-table :data="recentTasks" stripe>
            <el-table-column prop="id" label="ID" width="200" />
            <el-table-column prop="task_type" label="Type" width="120" />
            <el-table-column prop="status" label="Status">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="log_type" label="Log Type" width="120" />
            <el-table-column prop="created_at" label="Created" width="180" />
            <el-table-column label="Actions" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="viewTask(row)">View</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- Quick Actions -->
    <el-row :gutter="20" class="mt-20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>Quick Actions</span>
          </template>
          <div class="quick-actions">
            <el-button type="primary" @click="startAnalysis">
              <el-icon><Cpu /></el-icon>
              Start AI Analysis
            </el-button>
            <el-button type="success" @click="viewLogs">
              <el-icon><Document /></el-icon>
              View Logs
            </el-button>
            <el-button type="info" @click="generateReport">
              <el-icon><DocumentCopy /></el-icon>
              Generate Report
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'

const router = useRouter()

const logTrendChart = ref()
const errorDistributionChart = ref()

const stats = reactive({
  totalLogs: '1.2M',
  todayLogs: '45.6K',
  errorCount: '128',
  aiTasks: '24'
})

const recentTasks = ref([
  { id: 'task-001', task_type: 'auto', status: 'completed', log_type: 'all', created_at: '2024-04-17 08:00' },
  { id: 'task-002', task_type: 'manual', status: 'running', log_type: 'network', created_at: '2024-04-17 10:30' },
  { id: 'task-003', task_type: 'manual', status: 'pending', log_type: 'server', created_at: '2024-04-17 12:00' },
])

function getStatusType(status) {
  const types = {
    completed: 'success',
    running: 'primary',
    pending: 'info',
    failed: 'danger'
  }
  return types[status] || 'info'
}

function viewTask(task) {
  router.push(`/analysis?id=${task.id}`)
}

function startAnalysis() {
  router.push('/analysis')
}

function viewLogs() {
  router.push('/logs')
}

function generateReport() {
  router.push('/reports')
}

function initCharts() {
  // Log trend chart
  const trendChart = echarts.init(logTrendChart.value)
  trendChart.setOption({
    title: { text: 'Log Trend (Last 7 Days)', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: 'Logs',
        type: 'line',
        smooth: true,
        data: [120, 132, 101, 134, 90, 230, 210],
        areaStyle: { opacity: 0.3 }
      }
    ]
  })

  // Error distribution chart
  const errorChart = echarts.init(errorDistributionChart.value)
  errorChart.setOption({
    title: { text: 'Error Distribution', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [
      {
        name: 'Errors',
        type: 'pie',
        radius: '60%',
        data: [
          { value: 40, name: 'Network' },
          { value: 35, name: 'Server' },
          { value: 25, name: 'K8S' }
        ]
      }
    ]
  })
}

onMounted(() => {
  initCharts()
})
</script>

<style scoped lang="scss">
.stat-row {
  margin-bottom: 20px;
}

.quick-actions {
  display: flex;
  gap: 15px;
}
</style>